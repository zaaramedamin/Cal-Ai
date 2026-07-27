"""Diary endpoints: log food, read a day, edit and delete."""

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.profile import _targets_for
from app.core.dates import local_today
from app.core.deps import CurrentUser
from app.db.models.diary import DiaryEntry, MealSlot
from app.db.models.food import Food
from app.db.models.profile import UserProfile
from app.db.session import get_session
from app.schemas.diary import (
    DaySummary,
    DiaryEntryCreate,
    DiaryEntryRead,
    DiaryEntryUpdate,
    MealGroup,
    NutrientTotals,
)
from app.schemas.profile import MacroTargetsRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diary", tags=["diary"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: Nutrients a source may legitimately not report.
OPTIONAL_NUTRIENTS = ("sugars_g", "saturated_fat_g", "fibre_g", "sodium_mg")

PROFILE_REQUIRED = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Complete onboarding first."
)


async def _require_profile(session: AsyncSession, user_id: uuid.UUID) -> UserProfile:
    profile = await session.get(UserProfile, user_id)
    if profile is None:
        raise PROFILE_REQUIRED
    return profile


def _scale(per_100g: float | None, grams: float) -> float | None:
    """Scale a per-100 g nutrient to an actual quantity.

    None propagates as None rather than becoming 0. That is the whole discipline
    of this app in one line: "the source did not report fibre" must never turn
    into "this food contains no fibre" just because it passed through a
    multiplication.
    """
    if per_100g is None:
        return None
    return round(float(per_100g) * grams / 100.0, 2)


def _totals(entries: list[DiaryEntry]) -> NutrientTotals:
    """Sum a set of entries, tracking which totals are incomplete.

    Summing over missing values and presenting the result as a total would be
    inventing data by omission — the number would look authoritative and be
    quietly too low. So a nutrient that any entry failed to report is flagged,
    and the app says "at least 12 g".
    """

    def total_required(field: str) -> float:
        return round(sum(float(getattr(entry, field)) for entry in entries), 2)

    totals: dict[str, float | None] = {
        "kcal": total_required("kcal"),
        "protein_g": total_required("protein_g"),
        "carbs_g": total_required("carbs_g"),
        "fat_g": total_required("fat_g"),
    }

    partial: list[str] = []
    for field in OPTIONAL_NUTRIENTS:
        values = [getattr(entry, field) for entry in entries]
        known = [float(value) for value in values if value is not None]

        totals[field] = round(sum(known), 2) if known else None
        if entries and len(known) < len(values):
            partial.append(field)

    return NutrientTotals(**totals, partial=partial)


@router.post(
    "",
    response_model=DiaryEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log a food",
)
async def create_entry(
    payload: DiaryEntryCreate, user: CurrentUser, session: SessionDep
) -> DiaryEntryRead:
    """Log a food, snapshotting its nutrients at this quantity.

    The snapshot happens here, once, at log time. See `DiaryEntry` for why the
    numbers are copied rather than recalculated on every read.
    """
    profile = await _require_profile(session, user.id)

    food = await session.get(Food, payload.food_id)
    if food is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Food not found.")

    grams = float(payload.quantity_grams)
    today = local_today(profile.timezone)
    entry_date = payload.local_date or today

    if entry_date > today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot log food for a future date.",
        )

    entry = DiaryEntry(
        user_id=user.id,
        local_date=entry_date,
        meal_slot=payload.meal_slot.value,
        food_id=food.id,
        quantity_grams=grams,
        food_name=food.name,
        food_brand=food.brand,
        kcal=_scale(food.kcal, grams),
        protein_g=_scale(food.protein_g, grams),
        carbs_g=_scale(food.carbs_g, grams),
        fat_g=_scale(food.fat_g, grams),
        sugars_g=_scale(food.sugars_g, grams),
        saturated_fat_g=_scale(food.saturated_fat_g, grams),
        fibre_g=_scale(food.fibre_g, grams),
        sodium_mg=_scale(food.sodium_mg, grams),
        logged_at=datetime.now(UTC),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    return DiaryEntryRead.model_validate(entry)


@router.get("", response_model=DaySummary, summary="A day's diary and totals")
async def read_day(
    user: CurrentUser,
    session: SessionDep,
    day: Annotated[date | None, Query(description="Local date. Defaults to today.")] = None,
) -> DaySummary:
    """Everything logged on one local day, grouped by meal, against the target.

    The client sends which day it wants to *read* — that is fine, and necessary
    for browsing history. What it never does is decide which day something was
    *written* to.
    """
    profile = await _require_profile(session, user.id)
    target_day = day or local_today(profile.timezone)

    result = await session.execute(
        select(DiaryEntry)
        .where(DiaryEntry.user_id == user.id, DiaryEntry.local_date == target_day)
        .order_by(DiaryEntry.logged_at)
    )
    entries = list(result.scalars())

    from app.api.v1.profile import _latest_weight

    weight = await _latest_weight(session, user.id)
    if weight is None:
        raise PROFILE_REQUIRED
    targets = _targets_for(profile, float(weight.weight_kg))

    meals = [
        MealGroup(
            meal_slot=slot,
            entries=[
                DiaryEntryRead.model_validate(entry)
                for entry in entries
                if entry.meal_slot == slot.value
            ],
            totals=_totals([entry for entry in entries if entry.meal_slot == slot.value]),
        )
        for slot in MealSlot
    ]

    day_totals = _totals(entries)

    return DaySummary(
        local_date=target_day,
        meals=meals,
        totals=day_totals,
        target_calories=targets.calories,
        target_macros=MacroTargetsRead(**targets.macros.model_dump()),
        # Can go negative, deliberately. "-180 kcal" is information; clamping it
        # to zero would hide the fact that the user went over.
        remaining_calories=round(targets.calories - day_totals.kcal),
    )


@router.patch("/{entry_id}", response_model=DiaryEntryRead, summary="Edit an entry")
async def update_entry(
    entry_id: uuid.UUID,
    payload: DiaryEntryUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> DiaryEntryRead:
    """Change quantity or meal slot.

    Changing the quantity rescales the snapshot from the *original* per-gram
    values, derived from the stored snapshot rather than re-read from `foods`.
    That keeps an edit faithful to what the food was when it was logged, even if
    USDA has revised it since.
    """
    entry = await _owned_entry(session, entry_id, user.id)

    if payload.meal_slot is not None:
        entry.meal_slot = payload.meal_slot.value

    if payload.quantity_grams is not None:
        old_grams = float(entry.quantity_grams)
        new_grams = float(payload.quantity_grams)
        factor = Decimal(str(new_grams / old_grams))

        for field in ("kcal", "protein_g", "carbs_g", "fat_g", *OPTIONAL_NUTRIENTS):
            current = getattr(entry, field)
            if current is not None:
                setattr(entry, field, round(Decimal(str(current)) * factor, 2))

        entry.quantity_grams = new_grams

    await session.commit()
    await session.refresh(entry)
    return DiaryEntryRead.model_validate(entry)


@router.delete(
    "/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an entry"
)
async def delete_entry(entry_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    await _owned_entry(session, entry_id, user.id)
    await session.execute(delete(DiaryEntry).where(DiaryEntry.id == entry_id))
    await session.commit()


async def _owned_entry(
    session: AsyncSession, entry_id: uuid.UUID, user_id: uuid.UUID
) -> DiaryEntry:
    """Fetch an entry, 404ing unless it belongs to the caller.

    404 rather than 403 for someone else's entry: a 403 confirms the id exists,
    which lets an attacker enumerate valid ids. From the caller's position,
    "not yours" and "not there" should be indistinguishable.
    """
    result = await session.execute(
        select(DiaryEntry).where(DiaryEntry.id == entry_id, DiaryEntry.user_id == user_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found.")
    return entry
