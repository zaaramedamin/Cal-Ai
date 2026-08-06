"""Meals: compose from catalogue ingredients, log the whole plate at once."""

import logging
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import local_today
from app.core.deps import CurrentUser
from app.db.models.diary import DiaryEntry, MealSlot
from app.db.models.profile import UserProfile
from app.db.session import get_session
from app.schemas.diary import DiaryEntryRead
from app.schemas.meals import MealInput, MealRead
from app.services.meals import (
    create_meal,
    delete_meal,
    get_meal,
    list_meals,
    replace_meal,
    to_read,
    unknown_slugs,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meals", tags=["meals"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

MEAL_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found.")


class LogMeal(BaseModel):
    meal_slot: MealSlot
    day: date | None = None


async def _reject_unknown(session: AsyncSession, payload: MealInput) -> None:
    missing = await unknown_slugs(session, payload)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Not in the catalogue: {', '.join(missing)}",
        )


@router.get("", response_model=list[MealRead], summary="Your saved meals")
async def list_all(user: CurrentUser, session: SessionDep) -> list[MealRead]:
    return [to_read(meal) for meal in await list_meals(session, user.id)]


@router.post(
    "", response_model=MealRead, status_code=status.HTTP_201_CREATED, summary="Compose a meal"
)
async def create(payload: MealInput, user: CurrentUser, session: SessionDep) -> MealRead:
    await _reject_unknown(session, payload)
    return to_read(await create_meal(session, user.id, payload))


@router.get("/{meal_id}", response_model=MealRead, summary="Meal detail")
async def read_one(meal_id: str, user: CurrentUser, session: SessionDep) -> MealRead:
    meal = await get_meal(session, user.id, meal_id)
    if meal is None:
        raise MEAL_NOT_FOUND
    return to_read(meal)


@router.put("/{meal_id}", response_model=MealRead, summary="Replace a meal")
async def update(
    meal_id: str, payload: MealInput, user: CurrentUser, session: SessionDep
) -> MealRead:
    """Replace the name and the whole ingredient list.

    A full replacement rather than a patch, for the same reason recipes work this
    way: the builder screen holds the entire list in memory anyway, and
    per-ingredient endpoints would multiply both the round trips and the number
    of ways two concurrent edits can interleave into a state neither user meant.

    Already-logged diary entries are untouched — they carry their own snapshot.
    """
    await _reject_unknown(session, payload)
    meal = await replace_meal(session, user.id, meal_id, payload)
    if meal is None:
        raise MEAL_NOT_FOUND
    return to_read(meal)


@router.delete("/{meal_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a meal")
async def remove(meal_id: str, user: CurrentUser, session: SessionDep) -> None:
    if not await delete_meal(session, user.id, meal_id):
        raise MEAL_NOT_FOUND


@router.post(
    "/{meal_id}/log",
    response_model=DiaryEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log the whole meal in one entry",
)
async def log(
    meal_id: str, payload: LogMeal, user: CurrentUser, session: SessionDep
) -> DiaryEntryRead:
    """Write one diary entry carrying the meal's summed nutrition.

    One entry rather than one per ingredient, because that is what the user
    built: they assembled a plate and ate it, and a diary that explodes it back
    into six rows has thrown away the thing they took the trouble to define.

    The entry references neither a food nor a recipe — it carries only its
    snapshot, which the `at_most_one_source` constraint allows on purpose. That
    is not a gap: the snapshot is what makes a diary entry meaningful, and this
    one is as complete as any other. Editing or deleting the meal afterwards
    leaves this record exactly as it was, which is the entire point.
    """
    row = await get_meal(session, user.id, meal_id)
    if row is None:
        raise MEAL_NOT_FOUND

    meal = to_read(row)
    if not meal.items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="None of this meal's ingredients are still in the catalogue.",
        )

    profile = await session.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Complete onboarding first."
        )

    today = local_today(profile.timezone)
    entry_date = payload.day or today
    if entry_date > today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot log food for a future date.",
        )

    totals = meal.totals
    entry = DiaryEntry(
        user_id=user.id,
        local_date=entry_date,
        meal_slot=payload.meal_slot.value,
        quantity_grams=totals.total_grams,
        food_name=meal.name,
        food_brand=None,
        kcal=totals.kcal,
        protein_g=totals.protein_g,
        carbs_g=totals.carbs_g,
        fat_g=totals.fat_g,
        sugars_g=totals.sugars_g,
        saturated_fat_g=totals.saturated_fat_g,
        fibre_g=totals.fibre_g,
        sodium_mg=totals.sodium_mg,
        logged_at=datetime.now(UTC),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    logger.info("Logged meal %s (%d items) for user %s", meal_id, len(meal.items), user.id)
    return DiaryEntryRead.model_validate(entry)
