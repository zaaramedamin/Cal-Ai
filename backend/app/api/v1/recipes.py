"""Recipe endpoints: build, read, edit, delete, and log to the diary."""

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dates import local_today
from app.core.deps import CurrentUser
from app.db.models.diary import DiaryEntry, MealSlot
from app.db.models.food import Food
from app.db.models.profile import UserProfile
from app.db.models.recipe import Recipe, RecipeIngredient
from app.db.session import get_session
from app.nutrition.recipes import (
    IngredientNutrition,
    RecipeNutrition,
    calculate_recipe_nutrition,
)
from app.schemas.diary import DiaryEntryRead
from app.schemas.recipe import (
    IngredientRead,
    LogRecipeInput,
    RecipeInput,
    RecipeNutritionRead,
    RecipeRead,
    RecipeSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recipes", tags=["recipes"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

RECIPE_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found."
)


def _to_ingredient_nutrition(ingredient: RecipeIngredient) -> IngredientNutrition:
    food = ingredient.food
    return IngredientNutrition(
        grams=float(ingredient.grams),
        kcal=float(food.kcal),
        protein_g=float(food.protein_g),
        carbs_g=float(food.carbs_g),
        fat_g=float(food.fat_g),
        sugars_g=None if food.sugars_g is None else float(food.sugars_g),
        saturated_fat_g=None if food.saturated_fat_g is None else float(food.saturated_fat_g),
        fibre_g=None if food.fibre_g is None else float(food.fibre_g),
        sodium_mg=None if food.sodium_mg is None else float(food.sodium_mg),
    )


def _nutrition_of(recipe: Recipe) -> RecipeNutrition:
    return calculate_recipe_nutrition(
        [_to_ingredient_nutrition(item) for item in recipe.ingredients], recipe.servings
    )


def _to_read(recipe: Recipe) -> RecipeRead:
    nutrition = _nutrition_of(recipe)

    def block(values: dict[str, float | None]) -> RecipeNutritionRead:
        return RecipeNutritionRead(
            total_grams=nutrition.total_grams,
            partial=nutrition.partial,
            **values,  # type: ignore[arg-type]
        )

    return RecipeRead(
        id=recipe.id,
        name=recipe.name,
        servings=recipe.servings,
        ingredients=[
            IngredientRead(
                id=item.id,
                food_id=item.food_id,
                food_name=item.food.name,
                food_brand=item.food.brand,
                grams=float(item.grams),
                kcal=round(float(item.food.kcal) * float(item.grams) / 100.0, 2),
                kcal_per_100g=float(item.food.kcal),
                protein_g_per_100g=float(item.food.protein_g),
                carbs_g_per_100g=float(item.food.carbs_g),
                fat_g_per_100g=float(item.food.fat_g),
            )
            for item in recipe.ingredients
        ],
        total=block(nutrition.total),
        per_serving=block(nutrition.per_serving),
    )


async def _load_recipe(session: AsyncSession, recipe_id: uuid.UUID, user_id: uuid.UUID) -> Recipe:
    """Fetch a recipe with ingredients and their foods, or 404.

    Scoped to the owner in the query itself rather than checked afterwards. A
    filter that is part of the SELECT cannot be forgotten by a later edit the way
    a separate `if` can.

    `selectinload` two levels deep because a lazy load under asyncio raises
    MissingGreenlet — and it would fire once per ingredient, which is the N+1 as
    well as an error.
    """
    result = await session.execute(
        select(Recipe)
        .where(Recipe.id == recipe_id, Recipe.owner_id == user_id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.food))
    )
    recipe = result.scalar_one_or_none()
    if recipe is None:
        raise RECIPE_NOT_FOUND
    return recipe


async def _replace_ingredients(
    session: AsyncSession, recipe: Recipe, payload: RecipeInput
) -> None:
    """Validate every food exists, then set the ingredient list.

    All foods are fetched in one query rather than one lookup per ingredient —
    a twelve-ingredient recipe would otherwise be twelve round trips, and the
    validation must be complete before anything is written so a bad food id
    cannot leave a half-built recipe behind.
    """
    food_ids = [item.food_id for item in payload.ingredients]
    if len(set(food_ids)) != len(food_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="An ingredient appears more than once. Combine the quantities instead.",
        )

    found = await session.execute(select(Food.id).where(Food.id.in_(food_ids)))
    known = set(found.scalars())
    missing = [str(fid) for fid in food_ids if fid not in known]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown food id(s): {', '.join(missing)}",
        )

    await session.execute(
        delete(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe.id)
    )
    # Flush the deletes before inserting. Within one flush SQLAlchemy emits
    # inserts before deletes, so re-adding an ingredient that is still present
    # would trip the unique constraint on (recipe_id, food_id).
    await session.flush()

    for index, item in enumerate(payload.ingredients):
        session.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                food_id=item.food_id,
                grams=item.grams,
                sort_order=index,
            )
        )


@router.get("", response_model=list[RecipeSummary], summary="Your recipes")
async def list_recipes(user: CurrentUser, session: SessionDep) -> list[RecipeSummary]:
    result = await session.execute(
        select(Recipe)
        .where(Recipe.owner_id == user.id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.food))
        .order_by(Recipe.name)
    )

    summaries: list[RecipeSummary] = []
    for recipe in result.scalars():
        nutrition = _nutrition_of(recipe)
        summaries.append(
            RecipeSummary(
                id=recipe.id,
                name=recipe.name,
                servings=recipe.servings,
                ingredient_count=len(recipe.ingredients),
                kcal_per_serving=nutrition.per_serving["kcal"] or 0,
                protein_g_per_serving=nutrition.per_serving["protein_g"] or 0,
                carbs_g_per_serving=nutrition.per_serving["carbs_g"] or 0,
                fat_g_per_serving=nutrition.per_serving["fat_g"] or 0,
            )
        )
    return summaries


@router.post(
    "", response_model=RecipeRead, status_code=status.HTTP_201_CREATED, summary="Create a recipe"
)
async def create_recipe(
    payload: RecipeInput, user: CurrentUser, session: SessionDep
) -> RecipeRead:
    recipe = Recipe(owner_id=user.id, name=payload.name.strip(), servings=payload.servings)
    session.add(recipe)
    await session.flush()

    await _replace_ingredients(session, recipe, payload)
    await session.commit()

    logger.info("Recipe %s created for user %s", recipe.id, user.id)
    return _to_read(await _load_recipe(session, recipe.id, user.id))


@router.get("/{recipe_id}", response_model=RecipeRead, summary="Recipe detail")
async def read_recipe(
    recipe_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> RecipeRead:
    return _to_read(await _load_recipe(session, recipe_id, user.id))


@router.put("/{recipe_id}", response_model=RecipeRead, summary="Replace a recipe")
async def update_recipe(
    recipe_id: uuid.UUID, payload: RecipeInput, user: CurrentUser, session: SessionDep
) -> RecipeRead:
    """Replace name, servings and the whole ingredient list.

    A full replacement rather than a patch. The builder screen holds the entire
    ingredient list in memory anyway, and per-ingredient add/remove/reorder
    endpoints would multiply the number of round trips and the number of ways
    two edits can interleave into a state neither user intended.

    Existing diary entries are unaffected — they hold their own snapshot, which
    is exactly why swapping butter for oil does not rewrite last week's meals.
    """
    recipe = await _load_recipe(session, recipe_id, user.id)
    recipe.name = payload.name.strip()
    recipe.servings = payload.servings

    await _replace_ingredients(session, recipe, payload)
    await session.commit()

    # Drop everything from the identity map before re-reading.
    #
    # The ingredients were removed with a bulk DELETE, which the ORM does not
    # see, and this session is configured with expire_on_commit=False — so the
    # cached `recipe.ingredients` collection still holds the *old* rows and the
    # response would show the ingredients the user just replaced. Expunging
    # forces a genuine read.
    session.expunge_all()
    return _to_read(await _load_recipe(session, recipe_id, user.id))


@router.delete(
    "/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a recipe"
)
async def delete_recipe(recipe_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    recipe = await _load_recipe(session, recipe_id, user.id)
    await session.delete(recipe)
    await session.commit()


@router.post(
    "/{recipe_id}/log",
    response_model=DiaryEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log servings of a recipe",
)
async def log_recipe(
    recipe_id: uuid.UUID,
    payload: LogRecipeInput,
    user: CurrentUser,
    session: SessionDep,
    meal_slot: Annotated[MealSlot, Query()] = MealSlot.DINNER,
    day: Annotated[date | None, Query()] = None,
) -> DiaryEntryRead:
    """Log a portion of a recipe, snapshotting its nutrition.

    The snapshot is the whole point. Editing the recipe afterwards must not
    rewrite this meal — swap butter for oil in your Sunday chilli and every
    portion you ever logged would otherwise change retroactively.
    """
    profile = await session.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Complete onboarding first."
        )

    recipe = await _load_recipe(session, recipe_id, user.id)
    nutrition = _nutrition_of(recipe)
    servings = float(payload.servings)

    today = local_today(profile.timezone)
    entry_date = day or today
    if entry_date > today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot log food for a future date.",
        )

    def scaled(nutrient: str) -> float | None:
        value = nutrition.per_serving[nutrient]
        return None if value is None else round(value * servings, 2)

    entry = DiaryEntry(
        user_id=user.id,
        local_date=entry_date,
        meal_slot=meal_slot.value,
        recipe_id=recipe.id,
        # Grams as well as servings, so a day's weights stay summable whichever
        # way an entry was created.
        quantity_grams=round(nutrition.total_grams * servings / recipe.servings, 2),
        servings=servings,
        food_name=recipe.name,
        food_brand=None,
        kcal=scaled("kcal"),
        protein_g=scaled("protein_g"),
        carbs_g=scaled("carbs_g"),
        fat_g=scaled("fat_g"),
        sugars_g=scaled("sugars_g"),
        saturated_fat_g=scaled("saturated_fat_g"),
        fibre_g=scaled("fibre_g"),
        sodium_mg=scaled("sodium_mg"),
        logged_at=datetime.now(UTC),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    return DiaryEntryRead.model_validate(entry)
