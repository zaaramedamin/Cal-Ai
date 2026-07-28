"""Composing, reading and costing user meals.

A stored meal holds **references, not numbers** — slugs and amounts, nothing
else. The nutrition is resolved from the catalogue on every read.

That is the opposite of what the diary does, and both are right. A meal is a
definition ("this is what my breakfast is"), so it should reflect the current,
best-known values for its ingredients. A diary entry is a record ("this is what
I ate on Tuesday"), so it snapshots and never changes again. Storing totals on
the meal document would create a third copy that agrees with neither.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app.db.mongo import meals as meals_collection
from app.nutrition.recipes import IngredientNutrition, calculate_recipe_nutrition
from app.schemas.catalogue import CatalogueFood
from app.schemas.meals import MealInput, MealItemRead, MealRead, MealTotals
from app.services.catalogue import get_catalogue_food, grams_for

logger = logging.getLogger(__name__)


def parse_object_id(value: str) -> ObjectId | None:
    """Return an ObjectId, or None if the string is not one.

    Returning None rather than raising because every caller wants the same
    outcome — a 404. An unparseable id and an id that matches no document are the
    same fact from the user's side: no such meal.
    """
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


async def _resolve(
    items: list[dict[str, Any]],
) -> tuple[list[tuple[CatalogueFood, float]], list[str]]:
    """Look up each stored item in the catalogue.

    Returns the resolved (food, amount) pairs and the slugs that no longer exist.
    """
    resolved: list[tuple[CatalogueFood, float]] = []
    missing: list[str] = []

    for item in items:
        food = await get_catalogue_food(item["slug"])
        if food is None:
            missing.append(item["slug"])
            continue
        resolved.append((food, float(item["amount"])))

    return resolved, missing


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


async def to_read(doc: dict[str, Any]) -> MealRead:
    resolved, missing = await _resolve(doc.get("items", []))

    return MealRead(
        id=str(doc["_id"]),
        name=doc["name"],
        items=[
            MealItemRead(
                slug=food.slug,
                name_en=food.name_en,
                name_fr=food.name_fr,
                emoji=food.emoji,
                photo=food.photo,
                unit=food.unit,
                amount=amount,
                grams=grams_for(food, amount),
                kcal=round(food.kcal * grams_for(food, amount) / 100.0, 2),
            )
            for food, amount in resolved
        ],
        totals=compute_totals(resolved),
        created_at=doc["created_at"],
        missing_slugs=missing,
    )


async def unknown_slugs(payload: MealInput) -> list[str]:
    """Which of the submitted slugs are not in the catalogue.

    Checked before writing, so a typo cannot leave a half-valid meal behind.
    """
    missing = []
    for item in payload.items:
        if await get_catalogue_food(item.slug) is None:
            missing.append(item.slug)
    return missing


async def create_meal(user_id: str, payload: MealInput) -> dict[str, Any]:
    doc = {
        "user_id": user_id,
        "name": payload.name,
        "items": [{"slug": item.slug, "amount": item.amount} for item in payload.items],
        "created_at": datetime.now(UTC),
    }
    result = await meals_collection().insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info("Meal %s created for user %s", result.inserted_id, user_id)
    return doc


async def get_meal(user_id: str, meal_id: str) -> dict[str, Any] | None:
    """Fetch one meal, scoped to its owner.

    The `user_id` is part of the *query* rather than checked after the read. A
    filter that is part of the lookup cannot be forgotten by a later edit the way
    a separate `if` can — and here that `if` would be the only thing standing
    between a user and everybody else's meals.
    """
    oid = parse_object_id(meal_id)
    if oid is None:
        return None
    return await meals_collection().find_one({"_id": oid, "user_id": user_id})


async def list_meals(user_id: str) -> list[dict[str, Any]]:
    cursor = meals_collection().find({"user_id": user_id}).sort("name", 1)
    return [doc async for doc in cursor]


async def replace_meal(user_id: str, meal_id: str, payload: MealInput) -> dict[str, Any] | None:
    oid = parse_object_id(meal_id)
    if oid is None:
        return None

    return await meals_collection().find_one_and_update(
        {"_id": oid, "user_id": user_id},
        {
            "$set": {
                "name": payload.name,
                "items": [{"slug": item.slug, "amount": item.amount} for item in payload.items],
            }
        },
        # Without this the driver returns the document as it was *before* the
        # update, and the response would show the user the meal they just
        # replaced.
        return_document=True,
    )


async def delete_meal(user_id: str, meal_id: str) -> bool:
    oid = parse_object_id(meal_id)
    if oid is None:
        return False
    result = await meals_collection().delete_one({"_id": oid, "user_id": user_id})
    return result.deleted_count == 1
