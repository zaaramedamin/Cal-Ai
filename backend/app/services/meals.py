"""Composing, reading and costing user meals.

A stored meal holds **references, not numbers** — foods and amounts, nothing
else. The nutrition is resolved from the catalogue on every read.

That is the opposite of what the diary does, and both are right. A meal is a
definition ("this is what my breakfast is"), so it should reflect the current,
best-known values for its ingredients. A diary entry is a record ("this is what
I ate on Tuesday"), so it snapshots and never changes again. Storing totals on
the meal row would create a third copy that agrees with neither.

**What moving to Postgres changed.** Items used to store a catalogue *slug*,
which meant a meal could reference a food that no longer existed — hence
`missing_slugs` in the response. An item now carries a foreign key with
`ON DELETE RESTRICT`, so the database refuses to delete a food a meal still
needs. The field stays in the API for compatibility and is now always empty: the
case it reported is no longer representable.
"""

import logging
import uuid

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.food import Food
from app.db.models.meal import Meal, MealItem
from app.nutrition.recipes import IngredientNutrition, calculate_recipe_nutrition
from app.schemas.catalogue import CatalogueFood
from app.schemas.meals import MealInput, MealItemRead, MealRead, MealTotals
from app.services.catalogue import grams_for, to_catalogue_food

logger = logging.getLogger(__name__)


def parse_uuid(value: str) -> uuid.UUID | None:
    """Return a UUID, or None if the string is not one.

    Returning None rather than raising because every caller wants the same
    outcome — a 404. An unparseable id and an id that matches no row are the same
    fact from the user's side: no such meal.
    """
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


def _meal_query() -> Select[tuple[Meal]]:
    """A meal with everything needed to cost it, in one round trip.

    Three levels of `selectinload`: the items, each item's food, and each food's
    portions. Under asyncio a lazy load raises rather than silently issuing a
    query, so a missing level fails loudly in a test instead of becoming an N+1
    nobody notices in production.
    """
    return select(Meal).options(
        selectinload(Meal.items).selectinload(MealItem.food).selectinload(Food.portions)
    )


def _resolve(meal: Meal) -> list[tuple[CatalogueFood, float]]:
    """The (food, amount) pairs for a loaded meal, in the order they were added."""
    return [
        (to_catalogue_food(item.food), float(item.amount))
        for item in sorted(meal.items, key=lambda item: item.sort_order)
    ]


def compute_totals(resolved: list[tuple[CatalogueFood, float]]) -> MealTotals:
    """Sum the ingredients.

    Delegates to the recipe arithmetic with `servings=1` rather than re-adding
    the numbers here. That function already gets the two hard parts right — a
    missing nutrient stays missing instead of becoming zero, and nothing is
    rounded until the end so error does not accumulate per ingredient — and a
    second implementation of the same rules is a second place for them to drift.
    """
    nutrition = calculate_recipe_nutrition(
        [
            IngredientNutrition(
                grams=grams_for(food, amount),
                kcal=food.kcal,
                protein_g=food.protein_g,
                carbs_g=food.carbs_g,
                fat_g=food.fat_g,
                sugars_g=food.sugars_g,
                saturated_fat_g=food.saturated_fat_g,
                fibre_g=food.fibre_g,
                sodium_mg=food.sodium_mg,
            )
            for food, amount in resolved
        ],
        servings=1,
    )

    return MealTotals(
        total_grams=nutrition.total_grams,
        partial=nutrition.partial,
        **nutrition.total,  # type: ignore[arg-type]
    )


def _item_read(food: CatalogueFood, amount: float) -> MealItemRead:
    grams = grams_for(food, amount)
    return MealItemRead(
        slug=food.slug,
        name_en=food.name_en,
        name_fr=food.name_fr,
        emoji=food.emoji,
        photo=food.photo,
        unit=food.unit,
        amount=amount,
        grams=grams,
        grams_per_unit=food.grams_per_unit,
        kcal=round(food.kcal * grams / 100.0, 2),
        kcal_per_100g=food.kcal,
        protein_g_per_100g=food.protein_g,
        carbs_g_per_100g=food.carbs_g,
        fat_g_per_100g=food.fat_g,
    )


def to_read(meal: Meal) -> MealRead:
    resolved = _resolve(meal)

    return MealRead(
        id=str(meal.id),
        name=meal.name,
        items=[_item_read(food, amount) for food, amount in resolved],
        totals=compute_totals(resolved),
        created_at=meal.created_at,
        # Structurally impossible now — see the module docstring. Kept so the
        # response shape does not change under the app.
        missing_slugs=[],
    )


async def _foods_by_slug(session: AsyncSession, slugs: list[str]) -> dict[str, Food]:
    """Look up every submitted slug in one query rather than one query each."""
    if not slugs:
        return {}
    rows = (await session.execute(select(Food).where(Food.slug.in_(slugs)))).scalars().all()
    return {row.slug: row for row in rows}


async def unknown_slugs(session: AsyncSession, payload: MealInput) -> list[str]:
    """Which of the submitted slugs are not in the catalogue.

    Checked before writing, so a typo cannot leave a half-valid meal behind.
    """
    known = await _foods_by_slug(session, [item.slug for item in payload.items])
    return [item.slug for item in payload.items if item.slug not in known]


async def _write_items(session: AsyncSession, meal: Meal, payload: MealInput) -> None:
    """Replace a meal's items from the payload.

    Callers must have run `unknown_slugs` first. A slug missing here is a
    programming error rather than bad input, so the KeyError is left to surface:
    silently skipping the item would under-report the meal's calories, which is
    the one failure this app must never produce quietly.
    """
    known = await _foods_by_slug(session, [item.slug for item in payload.items])

    # An explicit DELETE rather than `meal.items.clear()`. Touching the
    # relationship reads it first, and on a freshly-flushed meal that is a lazy
    # load — which under asyncio raises `MissingGreenlet` rather than quietly
    # issuing a query. Going through the table skips the read entirely, which is
    # also one round trip instead of two.
    await session.execute(delete(MealItem).where(MealItem.meal_id == meal.id))

    for order, item in enumerate(payload.items):
        session.add(
            MealItem(
                meal_id=meal.id,
                food_id=known[item.slug].id,
                amount=item.amount,
                sort_order=order,
            )
        )
    await session.flush()


async def _reload(session: AsyncSession, meal_id: uuid.UUID) -> Meal:
    """Re-read with relationships loaded, so `to_read` never lazy-loads."""
    session.expire_all()
    query = _meal_query().where(Meal.id == meal_id)
    return (await session.execute(query)).scalar_one()


async def create_meal(session: AsyncSession, user_id: uuid.UUID, payload: MealInput) -> Meal:
    meal = Meal(user_id=user_id, name=payload.name)
    session.add(meal)
    await session.flush()

    await _write_items(session, meal, payload)
    await session.commit()

    logger.info("Meal %s created for user %s", meal.id, user_id)
    return await _reload(session, meal.id)


async def get_meal(session: AsyncSession, user_id: uuid.UUID, meal_id: str) -> Meal | None:
    """Fetch one meal, scoped to its owner.

    The `user_id` is part of the *query* rather than checked after the read. A
    filter that is part of the lookup cannot be forgotten by a later edit the way
    a separate `if` can — and here that `if` would be the only thing standing
    between a user and everybody else's meals.
    """
    parsed = parse_uuid(meal_id)
    if parsed is None:
        return None

    query = _meal_query().where(Meal.id == parsed, Meal.user_id == user_id)
    return (await session.execute(query)).scalar_one_or_none()


async def list_meals(session: AsyncSession, user_id: uuid.UUID) -> list[Meal]:
    query = _meal_query().where(Meal.user_id == user_id).order_by(Meal.name)
    return list((await session.execute(query)).scalars().all())


async def replace_meal(
    session: AsyncSession, user_id: uuid.UUID, meal_id: str, payload: MealInput
) -> Meal | None:
    meal = await get_meal(session, user_id, meal_id)
    if meal is None:
        return None

    meal.name = payload.name
    await _write_items(session, meal, payload)
    await session.commit()

    return await _reload(session, meal.id)


async def delete_meal(session: AsyncSession, user_id: uuid.UUID, meal_id: str) -> bool:
    meal = await get_meal(session, user_id, meal_id)
    if meal is None:
        return False

    await session.delete(meal)
    await session.commit()
    return True
