"""Progress: streaks, weekly intake, weight trend and BMI.

One endpoint returning everything the Progress screen renders. The screen would
otherwise make four requests on every focus — on mobile, one round trip that
answers the whole screen beats four clean ones.
"""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Date as SaDate
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import local_today
from app.core.deps import CurrentUser
from app.db.models.diary import DiaryEntry
from app.db.models.profile import UserProfile, WeightEntry
from app.db.session import get_session

router = APIRouter(prefix="/progress", tags=["progress"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class DayCalories(BaseModel):
    day: date
    kcal: float


class WeightPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recorded_on: date
    weight_kg: float


class ProgressRead(BaseModel):
    streak_days: int
    #: True when nothing is logged *today yet* but the streak is alive from
    #: yesterday — the UI shows "keep it going" rather than a broken streak.
    logged_today: bool

    last_7_days: list[DayCalories]
    weekly_average_kcal: float

    current_weight_kg: float | None
    target_weight_kg: float | None
    weight_series: list[WeightPoint]

    bmi: float | None
    bmi_category: str | None


def bmi_of(weight_kg: float, height_cm: float) -> tuple[float, str]:
    """BMI and its WHO category.

    Presented with the standard caveat baked into the category strings rather
    than a bare number: BMI ignores composition, so a muscular person reads
    "overweight". The screen shows the category label, and the label is honest.
    """
    metres = height_cm / 100.0
    bmi = round(weight_kg / (metres * metres), 1)

    if bmi < 18.5:
        category = "underweight"
    elif bmi < 25:
        category = "healthy"
    elif bmi < 30:
        category = "overweight"
    else:
        category = "obese"
    return bmi, category


def streak_from(days_logged: set[date], today: date) -> tuple[int, bool]:
    """Consecutive logged days, counting back from today or yesterday.

    A streak is *alive* if yesterday was logged, even when today is still empty —
    breaking someone's 30-day streak at breakfast because they have not logged
    lunch yet would make the number feel arbitrary and punitive. It only breaks
    once a whole day has actually been missed.
    """
    logged_today = today in days_logged

    anchor = today if logged_today else today - timedelta(days=1)
    streak = 0
    cursor = anchor
    while cursor in days_logged:
        streak += 1
        cursor -= timedelta(days=1)

    return streak, logged_today


@router.get("", response_model=ProgressRead, summary="Streak, intake and weight trend")
async def read_progress(user: CurrentUser, session: SessionDep) -> ProgressRead:
    profile = await session.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Complete onboarding first."
        )

    today = local_today(profile.timezone)

    # ---- streak ---------------------------------------------------------
    # Distinct dates only — the count of entries per day is irrelevant to a
    # streak, so fetching whole rows would move data for nothing.
    logged = await session.execute(
        select(DiaryEntry.local_date)
        .where(
            DiaryEntry.user_id == user.id,
            # Bounded: a streak longer than two years is beyond what anyone
            # renders, and an unbounded scan grows with the user's history.
            DiaryEntry.local_date >= today - timedelta(days=730),
        )
        .distinct()
    )
    days_logged = set(logged.scalars())
    streak, logged_today = streak_from(days_logged, today)

    # ---- last seven days of calories ------------------------------------
    week_start = today - timedelta(days=6)
    totals = await session.execute(
        select(
            cast(DiaryEntry.local_date, SaDate).label("day"),
            func.coalesce(func.sum(DiaryEntry.kcal), 0).label("kcal"),
        )
        .where(DiaryEntry.user_id == user.id, DiaryEntry.local_date >= week_start)
        .group_by(DiaryEntry.local_date)
    )
    by_day = {row.day: float(row.kcal) for row in totals}

    last_7 = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        last_7.append(DayCalories(day=day, kcal=round(by_day.get(day, 0.0), 1)))

    # Averaged over days that have entries, not over seven. Averaging in empty
    # days would tell someone who logged 2,000 kcal on each of three days that
    # they averaged 857 — technically defensible, practically misleading.
    logged_days = [point.kcal for point in last_7 if point.kcal > 0]
    weekly_average = round(sum(logged_days) / len(logged_days), 0) if logged_days else 0.0

    # ---- weight ----------------------------------------------------------
    weights = await session.execute(
        select(WeightEntry)
        .where(WeightEntry.user_id == user.id)
        .order_by(WeightEntry.recorded_on)
        .limit(365)
    )
    series = [WeightPoint.model_validate(entry) for entry in weights.scalars()]
    current = series[-1].weight_kg if series else None

    bmi = category = None
    if current is not None:
        bmi, category = bmi_of(float(current), float(profile.height_cm))

    return ProgressRead(
        streak_days=streak,
        logged_today=logged_today,
        last_7_days=last_7,
        weekly_average_kcal=weekly_average,
        current_weight_kg=float(current) if current is not None else None,
        target_weight_kg=(
            float(profile.target_weight_kg) if profile.target_weight_kg is not None else None
        ),
        weight_series=series,
        bmi=bmi,
        bmi_category=category,
    )
