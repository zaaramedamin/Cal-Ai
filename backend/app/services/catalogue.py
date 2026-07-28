"""Reading the catalogue, and getting a catalogue food into the diary.

The interesting part of this module is `materialise`. Everything else is a
lookup.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.food import Food, FoodSource
from app.db.mongo import food_items
from app.schemas.catalogue import CatalogueFood, CatalogueSection, UnitKind
from app.services.food_cache import upsert_food

logger = logging.getLogger(__name__)

#: Categories in the order the browse screen shows them. Explicit rather than
#: alphabetical: a person opening this screen is usually looking for the protein
#: in their meal, and "Carbs" coming before "Dairy" is an accident of the Latin
#: alphabet rather than a decision anyone made.
CATEGORY_ORDER = ("Protein", "Carbs", "Vegetables", "Fruit", "Dairy", "Fats", "Drinks")


def _category_rank(category: str) -> tuple[int, str]:
    """Sort key placing known categories first, unknown ones alphabetically after."""
    try:
        return (CATEGORY_ORDER.index(category), "")
    except ValueError:
        return (len(CATEGORY_ORDER), category)


async def list_catalogue() -> list[CatalogueSection]:
    """Every catalogue food, grouped into sections.

    One query, no pagination — see `CatalogueResponse` for why. Sorting happens
    here rather than in Mongo because the category order is a curatorial decision
    expressed as a Python tuple, not something an index can express.
    """
    cursor = food_items().find({}, {"_id": 0}).sort("order", 1)
    foods = [CatalogueFood.model_validate(doc) async for doc in cursor]

    grouped: dict[str, list[CatalogueFood]] = {}
    for food in foods:
        grouped.setdefault(food.category, []).append(food)

    return [
        CatalogueSection(category=category, foods=grouped[category])
        for category in sorted(grouped, key=_category_rank)
    ]


async def get_catalogue_food(slug: str) -> CatalogueFood | None:
    doc = await food_items().find_one({"slug": slug}, {"_id": 0})
    return None if doc is None else CatalogueFood.model_validate(doc)


def grams_for(food: CatalogueFood, amount: float) -> float:
    """Convert an amount in the food's own unit into grams.

    The whole point of the catalogue in one function. The user picks "2" for eggs
    and "250" for milk; the diary needs grams either way, and the conversion is
    the food's own `grams_per_unit` rather than an assumption made at the call
    site.
    """
    return round(amount * food.grams_per_unit, 2)


def format_amount(food: CatalogueFood, amount: float, *, french: bool = False) -> str:
    """How an amount reads back to the user: "2 eggs", "250 ml", "150 g".

    Used for the diary entry's name, so history shows what the user chose rather
    than the gram weight the server derived from it.
    """
    # Whole numbers print as "2", not "2.0"; halves stay "0.5" because half an
    # avocado is a real portion.
    tidy = f"{amount:g}"

    if food.unit is UnitKind.GRAMS:
        return f"{tidy} g"
    if food.unit is UnitKind.MILLILITRES:
        return f"{tidy} ml"

    name = food.name_fr if french else food.name_en
    return f"{tidy} × {name.lower()}"


async def materialise(session: AsyncSession, food: CatalogueFood) -> Food:
    """Find or create the Postgres `foods` row this catalogue entry stands for.

    **Why a catalogue food has to exist in two databases at once.**

    The diary is still Postgres, and a diary entry carries a foreign key to
    `foods`. A catalogue food is a Mongo document, so logging one needs a real
    `foods` row to point at. The alternative — logging with a null `food_id` and
    only the snapshot — would work, but it would quietly break everything built
    on that key: quick-add ("your usuals"), the food detail screen, and the
    suggestions engine all join through it.

    This is not duplication, because a catalogue food *is* a USDA food. It was
    seeded from a specific FDC id, and `upsert_food` is keyed on
    `(source, source_id)` — so the row it finds or creates is the same one an
    ordinary search for that food would have produced. Logging "1 verre de lait"
    and searching "milk" converge on one row rather than two.
    """
    return await upsert_food(
        session,
        {
            "source": FoodSource.USDA,
            # Guaranteed present: `seed_catalogue` only writes a food after USDA
            # returned a usable row, and the id is what proves the numbers are
            # traceable rather than typed in by hand.
            "source_id": str(food.source_id),
            "name": food.name_en,
            "brand": None,
            "is_liquid": food.unit is UnitKind.MILLILITRES,
            "kcal": food.kcal,
            "protein_g": food.protein_g,
            "carbs_g": food.carbs_g,
            "fat_g": food.fat_g,
            "sugars_g": food.sugars_g,
            "saturated_fat_g": food.saturated_fat_g,
            "fibre_g": food.fibre_g,
            "sodium_mg": food.sodium_mg,
            "portions": [
                {"label": portion.label_en, "grams": portion.grams}
                for portion in food.portions
            ],
        },
    )


def nutrients_for(food: CatalogueFood, grams: float) -> dict[str, Any]:
    """Scale a food's per-100 g values to a real quantity.

    `None` stays `None`. A food that does not report fibre does not report fibre
    at 150 g either, and turning that into `0.0` here would launder a gap into a
    confident figure.
    """
    factor = grams / 100.0

    def scale(value: float | None) -> float | None:
        return None if value is None else round(value * factor, 2)

    return {
        "kcal": round(food.kcal * factor, 2),
        "protein_g": round(food.protein_g * factor, 2),
        "carbs_g": round(food.carbs_g * factor, 2),
        "fat_g": round(food.fat_g * factor, 2),
        "sugars_g": scale(food.sugars_g),
        "saturated_fat_g": scale(food.saturated_fat_g),
        "fibre_g": scale(food.fibre_g),
        "sodium_mg": scale(food.sodium_mg),
    }
