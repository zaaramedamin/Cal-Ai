"""Portions for the imported tables — the units people actually eat in.

The dataset is entirely per 100 g and carries no serving sizes at all. That is
the single biggest practical gap in it: nobody eats 100 g of bread, they eat a
baguette or a slice, and asking somebody to estimate grams for every log is the
largest source of error in calorie tracking.

**Portions are curation, not measurement, and this codebase already says so.**
`catalogue_seed.py` puts it plainly: curation decides what the user sees, the
table decides what the numbers are, neither does the other's job. A portion
weight scales every nutrient on the row, though, so an invented one is a wrong
nutrition value by another route — which is why every entry below carries a
`basis` naming where its weight comes from, and why the list is short.

**What is deliberately absent.** There is no entry for pain tabouna, mlawi,
malsouka or bsissa. Those weights vary by bakery and by region and I have no
source for them — a plausible-looking number here would be exactly the kind of
quiet invention the rest of this project refuses. They are listed in
`WANTED` instead, so the gap is visible and fillable by somebody who knows.

Matching is by whole word against the normalised name, with an explicit veto
list per entry. It has to be loose enough to cover both spellings — INNTA writes
`PAIN, BAGUETTE` and Ciqual writes `Pain baguette` — and every loosening so far
has produced a wrong match that had to be vetoed by hand. Substring matching
gave *Bonbons, sucreries* the sugar-cube portion; adding word boundaries fixed
that and still gave *Pomme de terre* "1 apple = 182 g".

**Look at the output after changing anything here.** A portion on the wrong food
is worse than no portion: it looks authoritative and silently scales every
nutrient on the row.
"""

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.food import Food, FoodKind, FoodPortion, FoodSource
from app.services.food_import import normalise_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Serving:
    label_en: str
    label_fr: str
    grams: float
    default: bool = False


@dataclass(frozen=True)
class PortionSet:
    """Portions for every imported row whose name matches one of `names`."""

    #: Whole-word phrases. A row matches if its French or English name contains
    #: any of them as complete words.
    names: tuple[str, ...]

    servings: tuple[Serving, ...]

    #: Where these weights come from. Written out per entry because "how do you
    #: know a baguette is 250 g" is a fair question and the answer should not
    #: have to be reconstructed later.
    basis: str

    #: Phrases that veto a match, checked after `names`.
    #:
    #: Not decoration — every one of these is a wrong match that actually
    #: happened on this dataset. `pomme` matched *Pomme de terre* and handed
    #: potatoes "1 apple = 182 g"; `orange` matched *Jus d'orange* and gave a
    #: juice the weight of a whole fruit. French compounds a great many foods
    #: out of other foods' names, so a positive-only rule cannot be right here.
    excludes: tuple[str, ...] = ()


#: Weights whose basis is a legal definition, a published standard, or the
#: portion data USDA ships with the food itself. Nothing here is estimated.
PORTIONS: tuple[PortionSet, ...] = (
    PortionSet(
        names=("baguette",),
        excludes=("viennoise", "cereales"),
        servings=(
            Serving("1 piece (⅕ baguette)", "1 morceau (⅕ de baguette)", 50, default=True),
            Serving("Half a baguette", "Une demi-baguette", 125),
            Serving("1 baguette", "1 baguette", 250),
        ),
        # France fixes the baguette ordinaire at 250 g by trade convention and
        # Tunisian bakery baguettes are sold to the same size.
        basis="Standard baguette weight, 250 g",
    ),
    PortionSet(
        names=("pain complet", "pain de mie", "pain mie"),
        excludes=("tabouna", "mlawi", "baguette"),
        servings=(
            Serving("1 slice", "1 tranche", 30, default=True),
            Serving("2 slices", "2 tranches", 60),
        ),
        basis="Standard sandwich-loaf slice, 30 g",
    ),
    PortionSet(
        names=("oeuf", "oeufs", "egg", "eggs"),
        excludes=("jaune", "blanc", "yolk", "white", "poudre", "omelette"),
        servings=(
            Serving("1 medium egg", "1 œuf moyen", 50, default=True),
            Serving("2 medium eggs", "2 œufs moyens", 100),
        ),
        # EU egg grading: medium (M) is 53–63 g in shell, about 50 g edible.
        basis="EU egg grade M, ~50 g edible",
    ),
    PortionSet(
        names=("couscous",),
        excludes=("cuit", "prepare", "salade", "taboule"),
        servings=(
            Serving("1 serving, dry", "1 portion, sec", 80, default=True),
            Serving("1 large serving, dry", "1 grande portion, sèche", 120),
        ),
        basis="Package serving size, dry couscous",
    ),
    PortionSet(
        names=("huile d olive", "olive oil"),
        excludes=("olive noire", "olive verte"),
        servings=(
            Serving("1 teaspoon", "1 cuillère à café", 4.6, default=True),
            Serving("1 tablespoon", "1 cuillère à soupe", 13.6),
        ),
        # 5 ml and 15 ml at olive oil's density of 0.91 g/ml. Assuming water
        # would overstate a tablespoon by nearly 10%.
        basis="5 ml / 15 ml at density 0.91 g/ml",
    ),
    PortionSet(
        names=("sucre", "sugar"),
        excludes=("chocolat", "bonbon", "sucrerie", "lait", "boisson", "confiture"),
        servings=(
            Serving("1 teaspoon", "1 cuillère à café", 4, default=True),
            Serving("1 sugar cube", "1 morceau de sucre", 6),
        ),
        basis="Standard sugar cube 6 g; level teaspoon 4 g",
    ),
    PortionSet(
        names=("lait", "milk"),
        # Condensed and powdered milk are ingredients measured by the spoon, and
        # chocolate milk is its own drink; none of them takes "1 glass = 206 g".
        excludes=(
            "concentre", "poudre", "chocolat", "condensed", "powder",
            "ribot", "fermente", "fermented", "caille", "creme",
            # Yoghurt reaches this entry first because its name contains "lait"
            # — *Yaourt au lait entier* was handed a 206 g glass of milk, which
            # is not how anybody eats yoghurt.
            "yaourt", "yogurt", "yoghurt",
            # Rayeb and leben are drunk, but out of pots and glasses whose size
            # I have no source for. They are in WANTED for that reason, and
            # quietly giving them a milk glass here would contradict it.
            "rayeb", "leben",
        ),
        servings=(
            Serving("1 glass (200 ml)", "1 verre (200 ml)", 206, default=True),
            Serving("1 cup (250 ml)", "1 tasse (250 ml)", 258),
        ),
        # Milk is 1.03 g/ml, not 1.0.
        basis="200 ml / 250 ml at density 1.03 g/ml",
    ),
    PortionSet(
        names=("the", "cafe", "coffee", "tea"),
        excludes=("poudre", "soluble", "instantane", "au lait", "creme", "glace"),
        servings=(
            Serving("1 cup (200 ml)", "1 tasse (200 ml)", 200, default=True),
            Serving("1 small cup (100 ml)", "1 petite tasse (100 ml)", 100),
        ),
        basis="Volume at water density; both are ~99% water",
    ),
    PortionSet(
        names=("datte", "dattes", "date", "dates"),
        excludes=("pate", "sirop", "confiture"),
        servings=(
            Serving("1 date", "1 datte", 8, default=True),
            Serving("5 dates", "5 dattes", 40),
        ),
        basis="USDA FoodData Central portion, Deglet Noor date without pit",
    ),
    PortionSet(
        names=("banane", "banana"),
        excludes=("plantain", "jus", "chips", "seche"),
        servings=(
            Serving("1 banana", "1 banane", 118, default=True),
            Serving("1 large banana", "1 grande banane", 152),
        ),
        basis="USDA FoodData Central portions, medium and large",
    ),
    PortionSet(
        names=("pomme", "apple"),
        excludes=("pomme de terre", "jus", "compote", "potato"),
        servings=(Serving("1 apple", "1 pomme", 182, default=True),),
        basis="USDA FoodData Central portion, medium apple with skin",
    ),
    PortionSet(
        names=("orange",),
        excludes=("jus", "juice", "fleur", "confiture", "zeste"),
        servings=(Serving("1 orange", "1 orange", 131, default=True),),
        basis="USDA FoodData Central portion, medium orange",
    ),
    PortionSet(
        names=("yaourt", "yoghurt", "yogurt"),
        excludes=("boire", "drink", "glace"),
        servings=(
            Serving("1 pot", "1 pot", 125, default=True),
            Serving("1 large pot", "1 grand pot", 250),
        ),
        basis="Standard retail yoghurt pot, 125 g",
    ),
)


#: Foods that badly need a portion and are not getting an invented one.
#:
#: Every weight here varies by bakery, region or household, and I have no
#: source. Filling these in is a job for somebody who can weigh one — which is
#: a five-minute job for a person in Tunis and an act of fabrication for me.
WANTED: tuple[str, ...] = (
    "PAIN, TABOUNA — what does one loaf weigh?",
    "PAIN, MLAWI — one piece",
    "MALSOUKA / feuille de brik — one sheet",
    "BSISSA — one serving as usually mixed",
    "HARISSA — one teaspoon as actually used",
    "RAYEB / LEBEN — one glass or one pot as sold",
    "CHAMIA (halva) — one piece",
    "MAKROUD, KAAK WARKA — one piece",
)


def _words(value: str) -> str:
    """Normalised text with every run of punctuation turned into one space.

    Padded with spaces at both ends so a caller can search for `" sucre "` and
    get word-boundary matching out of a plain substring test.
    """
    return f" {re.sub(r'[^a-z0-9]+', ' ', normalise_key(value)).strip()} "


def _matches(food: Food, names: tuple[str, ...]) -> bool:
    """Whole words only.

    A bare substring test looked fine and was wrong on real data: `sucre`
    matched *Bonbons, sucreries de tous types* and *Chocolat instantané sucré*,
    handing both of them "1 sugar cube = 6 g". A portion attached to the wrong
    food is worse than no portion, because it looks authoritative and silently
    scales every nutrient on the row.
    """
    haystack = _words(food.name_fr or "") + _words(food.name)
    return any(_words(name) in haystack for name in names)


def _vetoed(food: Food, excludes: tuple[str, ...]) -> bool:
    haystack = _words(food.name_fr or "") + _words(food.name)
    return any(_words(term) in haystack for term in excludes)


async def apply_portions(
    session: AsyncSession, *, sources: tuple[str, ...] | None = None, replace: bool = False
) -> dict[str, int]:
    """Attach curated portions to imported rows that match by name.

    Existing portions are left alone unless `replace` is set, so re-running this
    cannot quietly change the meaning of a portion somebody has already logged
    against — a diary entry stores grams, but the label it was chosen by should
    keep saying the same thing.
    """
    wanted = sources or (FoodSource.INNTA, FoodSource.CIQUAL, FoodSource.USDA)
    rows = (
        (
            await session.execute(
                select(Food)
                .where(
                    Food.source.in_(list(wanted)),
                    Food.withdrawn_at.is_(None),
                    # Never a curated catalogue row.
                    #
                    # Those carry hand-written portions designed around the
                    # food's own unit — "1 fillet", "1 handful", "3 eggs" — and
                    # a generic "1 cup (200 ml)" landing on one would be a
                    # downgrade. They survived the first production run only
                    # because they already had portions, which is luck rather
                    # than a rule. Catalogue portions are `catalogue_seed`'s job.
                    Food.kind != FoodKind.CATALOGUE,
                )
                .options(selectinload(Food.portions))
            )
        )
        .scalars()
        .all()
    )

    counts = {"foods_given_portions": 0, "portions_added": 0, "already_had_portions": 0}

    for food in rows:
        entry = next(
            (p for p in PORTIONS if _matches(food, p.names) and not _vetoed(food, p.excludes)),
            None,
        )
        if entry is None:
            continue
        if food.portions and not replace:
            counts["already_had_portions"] += 1
            continue
        if food.portions:
            for existing in list(food.portions):
                await session.delete(existing)
            food.portions.clear()

        for serving in entry.servings:
            session.add(
                FoodPortion(
                    food_id=food.id,
                    label=serving.label_en,
                    label_fr=serving.label_fr,
                    grams=serving.grams,
                    # Null rather than a number: these are gram weights, not
                    # counts of the food's own unit. `amount` is the "2" in
                    # "2 eggs", and these rows have no such unit.
                    amount=None,
                    is_default=serving.default,
                )
            )
            counts["portions_added"] += 1
        counts["foods_given_portions"] += 1

    await session.commit()
    logger.info("Portions applied: %s", counts)
    return counts
