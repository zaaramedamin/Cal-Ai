"""Importing the merged Maghreb food dataset.

Three national tables in one file — INNTA (Tunisia), Ciqual (France) and USDA
FoodData Central — already mapped onto a shared per-100 g nutrient set. This
module turns those rows into `foods`.

**Why this dataset is the point of the project.** USDA measures American food and
Ciqual measures French food. Neither knows what pain tabouna, mlawi, rayeb, leben
or a figue de barbarie contains, and an app that cannot name the food someone in
Tunis just ate is not a tracker for them. The 228 INNTA rows are the reason this
import exists; the other 3,793 are useful company.

**Three rules the importer will not bend.**

*A blank stays blank.* The dataset nulls anything missing, garbled by OCR, or
below the limit of quantification, and those nulls are carried straight through
to nullable columns. Writing a `0` for an unreported nutrient would be inventing
data, and it would be invisible afterwards.

*A row without the four core values is not imported.* kcal, protein, carbs and
fat are what the app exists to report. A row missing one of them cannot be
logged usefully, and importing it as a half-food only moves the failure to the
moment somebody tries to eat it. They are counted and reported instead.

*A row whose macros contradict its own energy is imported and flagged, never
corrected.* See `suspect_reason`. The importer files a report for a human; it
has no opinion on which number is wrong, because it cannot have one.
"""

import json
import logging
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.food import (
    Food,
    FoodKind,
    FoodReport,
    FoodSource,
    ReportReason,
    ReportStatus,
)
from app.services.food_cache import upsert_food

logger = logging.getLogger(__name__)

#: Dataset source name -> what this app calls it.
#:
#: FoodDataCentral collapses onto the `usda` rows the live search already
#: caches: same upstream, same ids, so they share a row rather than becoming a
#: second copy under a different name.
SOURCES = {
    "INNTA": FoodSource.INNTA,
    "Ciqual": FoodSource.CIQUAL,
    "FoodDataCentral": FoodSource.USDA,
}

#: Without all four the row cannot be logged, so it is not imported at all.
CORE = ("energy_kcal", "protein_g", "carbohydrate_g", "fat_g")

#: Dataset key -> column, for the nutrients that are allowed to be missing.
OPTIONAL = {
    "sugars_total_g": "sugars_g",
    "saturated_fat_g": "saturated_fat_g",
    "fiber_g": "fibre_g",
    "sodium_mg": "sodium_mg",
}

#: How far a row's macros may sit from its stated energy before a human is asked.
#:
#: 4/4/9 is an approximation even when everything is right — fibre is partly
#: fermented rather than absorbed, polyols carry about 2.4 kcal/g against
#: sugar's 4, and organic acids in citrus contribute energy no macro column
#: reports. Ten percent would flag hundreds of perfectly good rows and teach
#: whoever reads the queue to skim it. Twenty-five percent is a transcription
#: error or a genuinely odd food, and both are worth a look.
SUSPECT_RATIO = 0.25

#: Rows below this are excluded from the check entirely: on a 12 kcal lettuce a
#: rounding difference of 4 kcal is 33% and means nothing.
SUSPECT_MIN_KCAL = 20.0


@dataclass
class ImportReport:
    """What the import did, in numbers a person can act on."""

    imported: int = 0
    skipped_incomplete: int = 0
    skipped_unknown_source: int = 0
    flagged: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    #: Names of rows dropped for missing a core value, so the gap is nameable
    #: rather than just counted.
    incomplete_names: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = ", ".join(f"{name} {count}" for name, count in sorted(self.by_source.items()))
        return (
            f"{self.imported} imported ({parts}); "
            f"{self.skipped_incomplete} skipped for missing core values; "
            f"{self.flagged} flagged for verification"
        )


def display_name(raw: str) -> str:
    """Make a table's name readable without changing what it says.

    INNTA is typed in full capitals — `PAIN, TABOUNA` — which is how printed
    tables are set and not how an app should shout at somebody logging lunch.
    Only wholly upper-case names are touched, so Ciqual's already-sentence-case
    names pass through untouched.

    Deliberately not `str.title()`: that produces "Pain, Tabouna" and mangles
    apostrophes into "Farine D'Orge". First letter up, rest down, which is
    French sentence case and what both tables use in prose.
    """
    stripped = raw.strip()
    letters = [c for c in stripped if c.isalpha()]
    if not letters or not all(c.isupper() for c in letters):
        return stripped
    return stripped[:1].upper() + stripped[1:].lower()


def suspect_reason(nutrients: dict[str, Any]) -> str | None:
    """Why this row deserves a human, or None if its arithmetic hangs together.

    Compares the energy the row states against the energy its own macros imply
    at 4/4/9. They should broadly agree; when they do not, one of the numbers is
    wrong and the importer cannot know which.

    Rows reporting alcohol are excluded: ethanol carries about 7 kcal/g and no
    macro column accounts for it, so every wine and beer would fail a check that
    only knows protein, carbohydrate and fat.
    """
    kcal = nutrients.get("energy_kcal")
    protein = nutrients.get("protein_g")
    carbs = nutrients.get("carbohydrate_g")
    fat = nutrients.get("fat_g")
    if None in (kcal, protein, carbs, fat) or kcal < SUSPECT_MIN_KCAL:
        return None

    if (nutrients.get("alcohol_g") or 0) > 0.5:
        return None

    # Fibre at 2 kcal/g, not 4, when the row reports it.
    #
    # These tables give carbohydrate *by difference*, which includes fibre — and
    # fibre is largely fermented rather than absorbed, so the EU regulation
    # counts it at 2 kcal/g. Applying a flat 4 to everything systematically
    # overstates the implied energy of vegetables, and it did: raw spinach and
    # raw mushroom both failed a check that was wrong about them, not about the
    # data. A queue with false positives in it is a queue people stop reading.
    fibre = nutrients.get("fiber_g") or 0
    digestible = max(carbs - fibre, 0)
    implied = 4 * protein + 4 * digestible + 2 * fibre + 9 * fat

    off = abs(implied - kcal) / kcal
    if off <= SUSPECT_RATIO:
        return None

    fibre_note = f", fibre {fibre:g} g" if fibre else ""
    return (
        f"States {kcal:g} kcal per 100 g, but its own macros imply "
        f"{implied:.0f} kcal ({off * 100:.0f}% apart): "
        f"protein {protein:g} g, carbohydrate {carbs:g} g, fat {fat:g} g{fibre_note}. "
        f"One of these is wrong — check the printed table before trusting it."
    )


def _source_reference(row: dict[str, Any]) -> str:
    """A human-followable pointer back to where the numbers were printed.

    A page number in the INNTA table is what turns "this looks wrong" into
    something a person can settle in a minute, so it goes into the note rather
    than being left in a column nobody reads.
    """
    ref = row.get("source_ref") or {}
    if "page" in ref:
        return f"INNTA table, page {ref['page']}"
    if "alim_code" in ref:
        return f"Ciqual alim_code {ref['alim_code']}"
    if "fdc_id" in ref:
        return f"FoodData Central id {ref['fdc_id']}"
    return row.get("id", "unknown")


def to_food_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """One dataset food as columns, or None when it cannot be imported.

    Names: the dataset's names are French for INNTA and Ciqual, so `name_fr`
    takes the French one and `name` falls back to it when there is no English
    name. A name is not translated here — a wrong food name in a nutrition app
    is worse than an untranslated one.
    """
    source = SOURCES.get(row.get("source", ""))
    if source is None:
        return None

    nutrients = row.get("nutrients") or {}
    if any(nutrients.get(key) is None for key in CORE):
        return None

    french = display_name(row.get("name_fr") or row.get("name") or "")

    # **INNTA's English column is not trusted, and Ciqual's is French anyway.**
    #
    # The Tunisian table was digitised by OCR and its English names came off
    # worst: `5EMOLINA FLOUR`, `POTATOE5, RAW`, `FRE5H LEMDN JUICE`, and — for
    # cabbage — `~ f'- ' CASSAGE, GREEN, RAW`. 23 of its 155 English names are
    # visibly damaged and that is only the ones a regex can spot. The French
    # names are the primary column and are clean.
    #
    # So an English-speaking user sees the French name. That is the same trade
    # this codebase makes everywhere else: an untranslated name is honest, a
    # mangled one is broken, and a wrong food name in a nutrition app is worse
    # than an unfamiliar one.
    english = display_name(row.get("name_en") or "") if source is FoodSource.USDA else ""
    if not english:
        english = french

    if not french:
        return None

    # FoodData Central shares its rows with the live USDA cache, which stores
    # the bare FDC id. Keeping the dataset's `fdc-` prefix would create a second
    # copy of every food the search has already seen.
    raw_id = str(row.get("id", ""))
    source_id = raw_id.removeprefix("fdc-") if source is FoodSource.USDA else raw_id
    if not source_id:
        return None

    columns: dict[str, Any] = {
        "source": source.value,
        "source_id": source_id[:64],
        "kind": FoodKind.REFERENCE,
        "name": english[:255],
        "name_fr": french[:255],
        # Explicitly null rather than absent: `upsert_food` refreshes a fixed
        # set of columns on conflict and reads every one of them. These tables
        # are national composition data, not products, so none of it is branded.
        "brand": None,
        "kcal": nutrients["energy_kcal"],
        "protein_g": nutrients["protein_g"],
        "carbs_g": nutrients["carbohydrate_g"],
        "fat_g": nutrients["fat_g"],
        "portions": [],
    }
    for key, column in OPTIONAL.items():
        columns[column] = nutrients.get(key)

    return columns


async def _flag(session: AsyncSession, food: Food, reason: str, reference: str) -> bool:
    """File an import check against a food, unless one is already open.

    Guarded because the partial unique index that stops a *person* reporting the
    same food twice does not apply here: `reporter_id` is null on these rows,
    and Postgres treats nulls as distinct in a unique index. Re-running the
    import would otherwise stack a fresh copy of every flag onto the queue.
    """
    existing = (
        await session.execute(
            select(FoodReport.id).where(
                FoodReport.food_id == food.id,
                FoodReport.reason == ReportReason.IMPORT_CHECK,
                FoodReport.status == ReportStatus.OPEN,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False

    session.add(
        FoodReport(
            food_id=food.id,
            # Null: nobody reported this, the importer did. The admin console
            # renders that differently, because "a person disagrees" and "the
            # arithmetic disagrees" deserve different amounts of trust.
            reporter_id=None,
            reason=ReportReason.IMPORT_CHECK,
            note=f"{reason} Source: {reference}."[:500],
        )
    )
    return True


async def import_dataset(
    session: AsyncSession,
    path: Path,
    *,
    only_source: str | None = None,
    limit: int | None = None,
) -> ImportReport:
    """Import the merged dataset, flagging what does not add up.

    `only_source` takes a dataset source name (`INNTA`, `Ciqual`,
    `FoodDataCentral`) so the Tunisian rows — the ones that matter — can be
    brought in and checked on their own before the other 3,793 arrive.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    foods = payload.get("foods", [])
    report = ImportReport()

    for raw in foods[:limit] if limit else foods:
        if only_source and raw.get("source") != only_source:
            continue

        columns = to_food_row(raw)
        if columns is None:
            if raw.get("source") not in SOURCES:
                report.skipped_unknown_source += 1
            else:
                report.skipped_incomplete += 1
                report.incomplete_names.append(raw.get("name", "?"))
            continue

        food = await upsert_food(session, dict(columns))
        report.imported += 1
        report.by_source[raw["source"]] = report.by_source.get(raw["source"], 0) + 1

        reason = suspect_reason(raw.get("nutrients") or {})
        if reason and await _flag(session, food, reason, _source_reference(raw)):
            report.flagged += 1

    await session.commit()
    logger.info("Dataset import finished: %s", report.summary())
    return report


#: Ligatures Unicode normalisation leaves alone.
#:
#: NFKD decomposes `é` into `e` + an accent, but `œ` has no decomposition at
#: all — it survives every normal form. Anything then stripping non-ASCII turns
#: `œuf` into `uf`, which is why the egg portions matched nothing at all on the
#: first run. French food tables are full of `œuf` and `bœuf`.
LIGATURES = str.maketrans({"œ": "oe", "æ": "ae", "Œ": "oe", "Æ": "ae"})


def normalise_key(value: str) -> str:
    """Accent- and case-insensitive form, for matching portion entries to rows.

    Written here rather than reusing the search tokeniser because the two want
    different things: search wants words, this wants one comparable string.
    """
    folded = unicodedata.normalize("NFKD", value.strip().lower().translate(LIGATURES))
    return "".join(c for c in folded if not unicodedata.combining(c))
