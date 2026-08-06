"""Importing the Maghreb food tables, and the portions that go on them.

Most of these guard against a specific wrong thing that actually happened while
building the importer against the real dataset. They are written that way on
purpose: every one names a mistake rather than a feature, because the mistakes
are what a future change is liable to reintroduce.

The theme is the same one that governs the photo import: **automated matching
cannot be trusted and has to be looked at.** Substring matching gave sugar cubes
to *Bonbons, sucreries*; adding word boundaries still gave *Pomme de terre* the
weight of an apple; and the dataset's own English names turned out to be OCR
wreckage.
"""

import json

import pytest
from sqlalchemy import select

from app.db.models.food import Food, FoodReport, FoodSource, ReportReason, ReportStatus
from app.services.food_import import (
    display_name,
    import_dataset,
    normalise_key,
    suspect_reason,
    to_food_row,
)
from app.services.portions_maghreb import PORTIONS, _matches, _vetoed, apply_portions


def dataset_row(**overrides):
    """One INNTA-shaped row, complete unless a test breaks it."""
    row = {
        "id": "innta-031",
        "source": "INNTA",
        "role": "tunisian_specific",
        "name": "PAIN, TABOUNA",
        "name_fr": "PAIN, TABOUNA",
        "name_en": None,
        "source_ref": {"page": 31},
        "nutrients": {
            "energy_kcal": 244.0,
            "protein_g": 8.01,
            "carbohydrate_g": 44.53,
            "fat_g": 3.16,
            "fiber_g": 1.62,
            "sugars_total_g": None,
            "saturated_fat_g": 0.42,
            "sodium_mg": 592.65,
        },
    }
    row.update(overrides)
    return row


# --------------------------------------------------------------------------- #
# Names
# --------------------------------------------------------------------------- #


def test_all_caps_names_become_readable() -> None:
    """Printed tables are set in capitals; an app should not shout at anybody."""
    assert display_name("PAIN, TABOUNA") == "Pain, tabouna"


def test_case_fixing_does_not_use_title_case() -> None:
    """`str.title()` produces "Farine D'Orge", which is not French.

    Sentence case is what both tables use in prose and what reads correctly with
    an apostrophe in the middle of a word.
    """
    assert display_name("FARINE D'ORGE") == "Farine d'orge"


def test_mixed_case_names_are_left_alone() -> None:
    """Ciqual is already sentence case and must pass through untouched."""
    assert display_name("Banane, chair sans peau, crue") == "Banane, chair sans peau, crue"


def test_innta_english_names_are_discarded() -> None:
    """The single most surprising thing in the dataset.

    INNTA's English column came off the OCR worst: `5EMOLINA FLOUR`,
    `POTATOE5, RAW`, `FRE5H LEMDN JUICE`, and for cabbage the immortal
    `~ f'- ' CASSAGE, GREEN, RAW`. Showing that to an English-speaking user is
    worse than showing them the clean French name.
    """
    row = dataset_row(name_fr="SEMOULE", name_en="5EMOLINA FLOUR UNENRICHED")

    columns = to_food_row(row)

    assert columns["name_fr"] == "Semoule"
    assert columns["name"] == "Semoule", "the garbled English name must not reach a user"


def test_usda_english_names_are_kept() -> None:
    """FoodData Central is an English source and its names are not OCR'd."""
    row = dataset_row(
        id="fdc-321358", source="FoodDataCentral", name_fr=None, name_en="Hummus, commercial"
    )

    assert to_food_row(row)["name"] == "Hummus, commercial"


def test_ligatures_survive_normalisation() -> None:
    """`œ` has no Unicode decomposition, so a naive fold turns `œuf` into `uf`.

    That is exactly what happened: the egg portions matched nothing at all on
    the first run, silently, because French food tables are full of `œuf`.
    """
    assert normalise_key("Œuf, frais").startswith("oeuf")
    assert "oe" in normalise_key("Bœuf")


# --------------------------------------------------------------------------- #
# What is and is not imported
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("missing", ["energy_kcal", "protein_g", "carbohydrate_g", "fat_g"])
def test_rows_missing_a_core_value_are_not_imported(missing: str) -> None:
    """A row without all four cannot be logged.

    Importing it as a half-food only moves the failure to the moment somebody
    tries to eat it.
    """
    row = dataset_row()
    row["nutrients"][missing] = None

    assert to_food_row(row) is None


def test_missing_optional_nutrients_stay_null() -> None:
    """The rule the whole app rests on: a blank stays blank.

    The dataset nulls anything missing, OCR-garbled or below the limit of
    quantification. Writing a `0` for an unreported nutrient would be inventing
    data, and it would be invisible afterwards.
    """
    columns = to_food_row(dataset_row())

    assert columns["sugars_g"] is None
    assert columns["fibre_g"] == 1.62


def test_unknown_sources_are_refused() -> None:
    assert to_food_row(dataset_row(source="SomeOtherTable")) is None


def test_foodcentral_ids_lose_their_prefix() -> None:
    """FDC rows share their row with the live USDA cache.

    Keeping the dataset's `fdc-` prefix would make a second copy of every food
    the search has already seen, under an id that matches nothing.
    """
    columns = to_food_row(dataset_row(id="fdc-321358", source="FoodDataCentral"))

    assert columns["source"] == FoodSource.USDA
    assert columns["source_id"] == "321358"


def test_innta_ids_are_kept_whole() -> None:
    assert to_food_row(dataset_row())["source_id"] == "innta-031"


# --------------------------------------------------------------------------- #
# The arithmetic check
# --------------------------------------------------------------------------- #


def test_a_row_that_adds_up_is_not_flagged() -> None:
    assert suspect_reason(dataset_row()["nutrients"]) is None


def test_a_row_that_contradicts_itself_is_flagged() -> None:
    """The real one this caught: INNTA's egg says 147 kcal with 13.5 g carbs.

    An egg has well under a gram of carbohydrate, so that column is damaged —
    but the importer cannot know whether the energy or the carbohydrate is the
    wrong number, so it says "check this" and changes nothing.
    """
    reason = suspect_reason(
        {"energy_kcal": 147.0, "protein_g": 12.58, "carbohydrate_g": 13.52, "fat_g": 9.94}
    )

    assert reason is not None
    assert "147" in reason and "check the printed table" in reason


def test_fibre_counts_at_two_kcal_not_four() -> None:
    """Otherwise every vegetable is flagged and the queue becomes unreadable.

    These tables give carbohydrate *by difference*, which includes fibre, and
    fibre is largely fermented rather than absorbed. Raw spinach and raw
    mushroom both failed a check that was wrong about them, not about the data.
    """
    spinach = {
        "energy_kcal": 23.0,
        "protein_g": 2.86,
        "carbohydrate_g": 3.63,
        "fat_g": 0.39,
        "fiber_g": 2.2,
    }

    assert suspect_reason(spinach) is None


def test_alcohol_is_excluded_from_the_check() -> None:
    """Ethanol carries about 7 kcal/g and no macro column accounts for it, so
    every wine and beer would fail a check that only knows protein, carbohydrate
    and fat."""
    wine = {
        "energy_kcal": 85.0,
        "protein_g": 0.1,
        "carbohydrate_g": 2.6,
        "fat_g": 0.0,
        "alcohol_g": 10.6,
    }

    assert suspect_reason(wine) is None


def test_very_low_energy_rows_are_not_checked() -> None:
    """On a 12 kcal lettuce a 4 kcal rounding difference is 33% and means
    nothing."""
    assert (
        suspect_reason(
            {"energy_kcal": 12.0, "protein_g": 1.0, "carbohydrate_g": 2.0, "fat_g": 0.2}
        )
        is None
    )


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #


@pytest.fixture
def dataset_file(tmp_path):
    """Two good rows and one that contradicts itself."""
    payload = {
        "metadata": {"title": "test"},
        "foods": [
            dataset_row(),
            dataset_row(id="innta-002", name_fr="COUSCOUS SEC", nutrients={
                "energy_kcal": 350.0, "protein_g": 12.0, "carbohydrate_g": 72.0, "fat_g": 1.0,
            }),
            dataset_row(id="innta-003", name_fr="ŒUF, FRAIS", source_ref={"page": 77}, nutrients={
                "energy_kcal": 147.0, "protein_g": 12.58, "carbohydrate_g": 13.52, "fat_g": 9.94,
            }),
        ],
    }
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


async def test_import_stores_foods_and_flags_the_odd_one(session, dataset_file) -> None:
    report = await import_dataset(session, dataset_file)

    assert report.imported == 3
    assert report.flagged == 1

    flagged = (
        (
            await session.execute(
                select(FoodReport).where(FoodReport.reason == ReportReason.IMPORT_CHECK)
            )
        )
        .scalars()
        .all()
    )
    assert len(flagged) == 1
    # The page number is what turns "this looks wrong" into a minute's work.
    assert "page 77" in flagged[0].note
    assert flagged[0].reporter_id is None, "nobody reported this; the arithmetic did"


async def test_reimporting_does_not_stack_duplicate_flags(session, dataset_file) -> None:
    """The partial unique index that stops a person reporting twice does not
    apply here: `reporter_id` is null, and Postgres treats nulls as distinct in a
    unique index. Without an explicit guard, every re-run would pile another
    copy of every flag onto the queue.
    """
    await import_dataset(session, dataset_file)
    second = await import_dataset(session, dataset_file)

    assert second.flagged == 0
    total = (
        await session.execute(
            select(FoodReport).where(FoodReport.reason == ReportReason.IMPORT_CHECK)
        )
    ).scalars().all()
    assert len(total) == 1


async def test_only_source_filters_the_import(session, dataset_file) -> None:
    """228 Tunisian rows are reviewable; 4,021 are not."""
    report = await import_dataset(session, dataset_file, only_source="Ciqual")

    assert report.imported == 0


async def test_a_resolved_flag_can_be_raised_again(session, dataset_file) -> None:
    """Only *open* flags block a new one, so a re-import after a wrong dismissal
    still asks."""
    await import_dataset(session, dataset_file)
    flag = (
        await session.execute(
            select(FoodReport).where(FoodReport.reason == ReportReason.IMPORT_CHECK)
        )
    ).scalar_one()
    flag.status = ReportStatus.DISMISSED
    await session.commit()

    assert (await import_dataset(session, dataset_file)).flagged == 1


# --------------------------------------------------------------------------- #
# Portions
# --------------------------------------------------------------------------- #


def food(name_fr: str, name: str | None = None) -> Food:
    return Food(
        source=FoodSource.INNTA,
        source_id="x",
        name=name or name_fr,
        name_fr=name_fr,
        kcal=1,
        protein_g=1,
        carbs_g=1,
        fat_g=1,
    )


def entry(*names: str):
    return next(p for p in PORTIONS if all(n in p.names for n in names))


def test_portions_match_whole_words_not_substrings() -> None:
    """`sucre` matched *Bonbons, sucreries de tous types* and handed a bag of
    sweets "1 sugar cube = 6 g"."""
    sugar = entry("sucre")

    assert _matches(food("Sucre"), sugar.names)
    assert not _matches(food("Bonbons, sucreries de tous types"), sugar.names)


def test_potatoes_do_not_get_the_weight_of_an_apple() -> None:
    """Word boundaries were not enough: *Pomme de terre* is a whole-word match
    for *pomme*. French compounds a great many foods out of other foods' names.
    """
    apple = entry("pomme")

    assert not _vetoed(food("Pomme, fraîche"), apple.excludes)
    assert _vetoed(food("Pomme de terre, crue"), apple.excludes)


def test_juice_does_not_get_the_weight_of_whole_fruit() -> None:
    orange = entry("orange")

    assert _vetoed(food("Jus d'orange, frais"), orange.excludes)


def test_yoghurt_is_not_a_glass_of_milk() -> None:
    """*Yaourt au lait entier* reaches the milk entry first, because its name
    contains `lait`."""
    milk = entry("lait")

    assert _vetoed(food("Yaourt au lait entier, aux fruits"), milk.excludes)


def test_rayeb_is_left_without_a_portion() -> None:
    """It is in `WANTED` — its pot size varies and I have no source.

    It reached the milk entry through its *English* name, which INNTA renders as
    the OCR-mangled `Whole milk-producer -3. 7% fat`. Quietly giving it a milk
    glass would contradict the list that says the weight is unknown.
    """
    milk = entry("lait")

    assert _vetoed(food("Rayeb", "Whole milk-producer -3. 7% fat"), milk.excludes)


def test_every_portion_set_states_where_its_weights_come_from() -> None:
    """A portion scales every nutrient on the row, so an invented one is a wrong
    nutrition value by another route."""
    for entry_ in PORTIONS:
        assert entry_.basis.strip(), f"{entry_.names} has no stated basis"
        assert entry_.servings, f"{entry_.names} has no servings"


def test_exactly_one_default_portion_per_set() -> None:
    """Two defaults means the food detail screen picks whichever came back
    first, which is not a decision anybody made."""
    for entry_ in PORTIONS:
        defaults = [s for s in entry_.servings if s.default]
        assert len(defaults) == 1, f"{entry_.names} has {len(defaults)} defaults"


async def test_applying_portions_attaches_them(session, dataset_file) -> None:
    await import_dataset(session, dataset_file)

    counts = await apply_portions(session)

    assert counts["foods_given_portions"] >= 1
    couscous = (
        await session.execute(select(Food).where(Food.name_fr == "Couscous sec"))
    ).scalar_one()
    await session.refresh(couscous, ["portions"])
    assert {float(p.grams) for p in couscous.portions} == {80.0, 120.0}


async def test_reapplying_leaves_existing_portions_alone(session, dataset_file) -> None:
    """A diary entry stores grams, but the label it was chosen by should keep
    saying the same thing."""
    await import_dataset(session, dataset_file)
    await apply_portions(session)

    second = await apply_portions(session)

    assert second["portions_added"] == 0
    assert second["already_had_portions"] >= 1
