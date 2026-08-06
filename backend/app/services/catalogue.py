"""Reading the catalogue, and getting a catalogue food into the diary.

The catalogue lives in the `foods` table, marked `kind = 'catalogue'`, alongside
the USDA search cache. It used to be a separate MongoDB collection, and the cost
of that was a function called `materialise` whose entire job was copying a Mongo
document into a Postgres row so a diary entry had a foreign key to point at. One
table deletes it: a catalogue food *is* a `foods` row, so logging one is an
ordinary insert with an ordinary foreign key.

What remains here is a lookup, a converter to the API shape, and three pure
functions that do the unit arithmetic.
"""

import logging
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.food import Food, FoodKind
from app.schemas.catalogue import CatalogueFood, CatalogueSection, Portion, UnitKind

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


def _catalogue_query() -> Select[tuple[Food]]:
    """Catalogue rows with their portions, in curatorial order.

    `selectinload` rather than a lazy relationship: under asyncio a lazy load
    raises instead of quietly issuing a query, which is the right behaviour and
    also means forgetting this is a crash rather than an N+1 nobody notices.
    """
    return (
        select(Food)
        .where(Food.kind == FoodKind.CATALOGUE)
        # A catalogue food upheld as wrong stops being offered. Same reasoning as
        # in `food_cache.search_local`: withdrawn, not deleted, so diary entries
        # that already reference it still render.
        .where(Food.withdrawn_at.is_(None))
        .options(selectinload(Food.portions))
        .order_by(Food.sort_order)
    )


def to_catalogue_food(row: Food) -> CatalogueFood:
    """The API shape, from a database row.

    Numeric columns arrive as `Decimal` and Pydantic coerces them to float on the
    way in, which is where that boundary belongs: the database keeps exact
    decimals, the JSON carries numbers.
    """
    return CatalogueFood(
        slug=row.slug,
        name_en=row.name,
        name_fr=row.name_fr,
        category=row.category,
        emoji=row.emoji,
        photo=row.photo,
        unit=UnitKind(row.unit),
        grams_per_unit=row.grams_per_unit,
        kcal=row.kcal,
        protein_g=row.protein_g,
        carbs_g=row.carbs_g,
        fat_g=row.fat_g,
        fibre_g=row.fibre_g,
        sugars_g=row.sugars_g,
        saturated_fat_g=row.saturated_fat_g,
        sodium_mg=row.sodium_mg,
        source=row.source,
        source_id=row.source_id,
        order=row.sort_order,
        portions=[
            Portion(
                label_en=portion.label,
                # Catalogue portions always carry both languages. The fallback
                # only matters for a row hand-edited in the database, and showing
                # the English twice is better than showing nothing.
                label_fr=portion.label_fr or portion.label,
                amount=portion.amount if portion.amount is not None else portion.grams,
                grams=portion.grams,
                is_default=portion.is_default,
            )
            for portion in row.portions
        ],
    )


async def list_catalogue(session: AsyncSession) -> list[CatalogueSection]:
    """Every catalogue food, grouped into sections.

    One query, no pagination — see `CatalogueResponse` for why. Grouping happens
    here rather than in SQL because the category order is a curatorial decision
    expressed as a Python tuple, not something an index can express.
    """
    rows = (await session.execute(_catalogue_query())).scalars().all()

    grouped: dict[str, list[CatalogueFood]] = {}
    for row in rows:
        grouped.setdefault(row.category, []).append(to_catalogue_food(row))

    return [
        CatalogueSection(category=category, foods=grouped[category])
        for category in sorted(grouped, key=_category_rank)
    ]


async def get_catalogue_row(session: AsyncSession, slug: str) -> Food | None:
    """The database row, for callers that need its id to write a foreign key."""
    query = _catalogue_query().where(Food.slug == slug)
    return (await session.execute(query)).scalar_one_or_none()


async def get_catalogue_food(session: AsyncSession, slug: str) -> CatalogueFood | None:
    row = await get_catalogue_row(session, slug)
    return None if row is None else to_catalogue_food(row)


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
