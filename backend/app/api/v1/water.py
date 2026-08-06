"""Water intake: log a drink, read the day, undo a mistake."""

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import local_today
from app.core.deps import CurrentUser
from app.db.models.profile import UserProfile
from app.db.models.water import WaterEntry
from app.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/water", tags=["water"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: Matches the CHECK constraint on the table. Duplicated on purpose: the database
#: is the guarantee, this is the *message*. Without it a 5001 ml entry becomes a
#: 500 from a constraint violation instead of a 422 naming the field.
MAX_DRINK_ML = 5000


class LogWater(BaseModel):
    millilitres: int = Field(gt=0, le=MAX_DRINK_ML)
    #: Which local day to file it under. Absent means today; supplied only when
    #: back-filling, exactly as the diary works.
    day: date | None = None


class WaterEntryRead(BaseModel):
    id: uuid.UUID
    millilitres: int
    logged_at: datetime


class WaterDay(BaseModel):
    """A day's intake.

    `goal_ml` is nullable and the null is meaningful: it means the user has not
    set one. The client shows the total without a denominator rather than
    inventing a target — every "two litres a day" figure in circulation is a rule
    of thumb, and this app does not print rules of thumb as personal numbers.
    """

    day: date
    total_ml: int
    goal_ml: int | None
    entries: list[WaterEntryRead]


async def _profile_or_404(session: AsyncSession, user_id: uuid.UUID) -> UserProfile:
    profile = await session.get(UserProfile, user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Complete onboarding first."
        )
    return profile


@router.get("", response_model=WaterDay, summary="A day's water intake")
async def read_day(
    user: CurrentUser,
    session: SessionDep,
    day: Annotated[date | None, Query()] = None,
) -> WaterDay:
    profile = await _profile_or_404(session, user.id)
    target = day or local_today(profile.timezone)

    rows = (
        (
            await session.execute(
                select(WaterEntry)
                .where(WaterEntry.user_id == user.id, WaterEntry.local_date == target)
                .order_by(WaterEntry.logged_at)
            )
        )
        .scalars()
        .all()
    )

    return WaterDay(
        day=target,
        total_ml=sum(row.millilitres for row in rows),
        goal_ml=profile.water_goal_ml,
        entries=[
            WaterEntryRead(id=row.id, millilitres=row.millilitres, logged_at=row.logged_at)
            for row in rows
        ],
    )


@router.post(
    "",
    response_model=WaterDay,
    status_code=status.HTTP_201_CREATED,
    summary="Log a drink",
)
async def log_water(payload: LogWater, user: CurrentUser, session: SessionDep) -> WaterDay:
    """Record a drink and return the whole day.

    The day rather than the entry, because the caller is a screen showing a
    total: returning just the new row would make it either re-fetch or add the
    number itself, and a client doing its own arithmetic is a client that can
    disagree with the server.
    """
    profile = await _profile_or_404(session, user.id)
    today = local_today(profile.timezone)
    target = payload.day or today

    if target > today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot log water for a future date.",
        )

    session.add(
        WaterEntry(
            user_id=user.id,
            local_date=target,
            millilitres=payload.millilitres,
            logged_at=datetime.now(UTC),
        )
    )
    await session.commit()

    logger.info("Logged %d ml for user %s", payload.millilitres, user.id)
    return await read_day(user=user, session=session, day=target)


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Undo a logged drink",
)
async def remove_water(entry_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    """Delete one entry.

    `user_id` is part of the statement rather than checked after loading the row.
    A filter that is part of the query cannot be forgotten by a later edit the
    way a separate `if` can — and here that `if` is the only thing between a user
    and deleting someone else's data.
    """
    result = await session.execute(
        delete(WaterEntry).where(WaterEntry.id == entry_id, WaterEntry.user_id == user.id)
    )
    await session.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such entry.")


class SetWaterGoal(BaseModel):
    #: Null clears the goal, which is a real choice rather than a missing value —
    #: see `WaterDay.goal_ml`.
    goal_ml: int | None = Field(default=None, ge=500, le=10_000)


@router.put("/goal", response_model=WaterDay, summary="Set or clear the daily goal")
async def set_goal(payload: SetWaterGoal, user: CurrentUser, session: SessionDep) -> WaterDay:
    profile = await _profile_or_404(session, user.id)
    profile.water_goal_ml = payload.goal_ml
    await session.commit()

    return await read_day(user=user, session=session, day=None)


@router.get("/history", summary="Daily totals, most recent first")
async def read_history(
    user: CurrentUser,
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
) -> list[dict[str, int | str]]:
    """Totals per day, for a chart.

    Aggregated in SQL rather than by loading every entry and summing in Python:
    ninety days of drinks is a few hundred rows to transfer and discard, and the
    database does this in one pass.
    """
    profile = await _profile_or_404(session, user.id)
    today = local_today(profile.timezone)

    rows = (
        await session.execute(
            select(
                WaterEntry.local_date,
                func.sum(WaterEntry.millilitres).label("total"),
            )
            .where(WaterEntry.user_id == user.id)
            .group_by(WaterEntry.local_date)
            .order_by(WaterEntry.local_date.desc())
            .limit(days)
        )
    ).all()

    return [{"day": day.isoformat(), "total_ml": int(total)} for day, total in rows if day <= today]
