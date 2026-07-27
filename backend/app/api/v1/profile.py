"""Profile, targets and weight endpoints."""

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import local_today
from app.core.deps import CurrentUser
from app.db.models.profile import UserProfile, WeightEntry
from app.db.session import get_session
from app.nutrition.targets import (
    ActivityLevel,
    Goal,
    InvalidBodyStats,
    Sex,
    calculate_targets,
)
from app.schemas.profile import (
    ProfileInput,
    ProfileRead,
    ProfileWithTargets,
    TargetsRead,
    WeightEntryInput,
    WeightEntryRead,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

PROFILE_REQUIRED = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Complete onboarding first.",
)


def age_on(birth_date: date, today: date) -> int:
    """Whole years elapsed.

    The `<` comparison on (month, day) is the entire subtlety: born 1 March, on
    28 February you are still the younger age. Subtracting years alone is off by
    one for everyone who has not yet had their birthday this year.
    """
    had_birthday = (today.month, today.day) >= (birth_date.month, birth_date.day)
    return today.year - birth_date.year - (0 if had_birthday else 1)


async def _latest_weight(session: AsyncSession, user_id: uuid.UUID) -> WeightEntry | None:
    result = await session.execute(
        select(WeightEntry)
        .where(WeightEntry.user_id == user_id)
        .order_by(WeightEntry.recorded_on.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _targets_for(profile: UserProfile, weight_kg: float) -> TargetsRead:
    """Recalculate from stored stats.

    Targets are computed on read rather than stored. They are a pure function of
    the profile and the latest weight, so persisting them would create a second
    copy that goes stale the moment either input changes — and a stale calorie
    target is worse than no target at all.
    """
    try:
        result = calculate_targets(
            sex=Sex(profile.sex),
            age_years=age_on(profile.birth_date, local_today(profile.timezone)),
            height_cm=float(profile.height_cm),
            weight_kg=weight_kg,
            activity_level=ActivityLevel(profile.activity_level),
            goal=Goal(profile.goal),
        )
    except InvalidBodyStats as exc:
        # Reachable if a profile was stored before a rule tightened, or if a user
        # aged past 100. Better a clear 422 than a 500 with a traceback.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    return TargetsRead.model_validate(result, from_attributes=True)


@router.get("", response_model=ProfileWithTargets, summary="Profile and current targets")
async def read_profile(user: CurrentUser, session: SessionDep) -> ProfileWithTargets:
    profile = await session.get(UserProfile, user.id)
    if profile is None:
        raise PROFILE_REQUIRED

    weight = await _latest_weight(session, user.id)
    if weight is None:
        raise PROFILE_REQUIRED

    return ProfileWithTargets(
        profile=ProfileRead.model_validate(profile),
        current_weight_kg=float(weight.weight_kg),
        targets=_targets_for(profile, float(weight.weight_kg)),
    )


@router.put("", response_model=ProfileWithTargets, summary="Complete or update onboarding")
async def upsert_profile(
    payload: ProfileInput, user: CurrentUser, session: SessionDep
) -> ProfileWithTargets:
    """Create or replace the profile, and record the weight.

    PUT rather than POST because it is idempotent: onboarding and later edits are
    the same operation, and sending it twice leaves the same state. That also
    means the app does not need to know whether a profile already exists.
    """
    today = local_today(payload.timezone)

    if age_on(payload.birth_date, today) < 13:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="CalAi is not intended for under-13s.",
        )

    profile = await session.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id)
        session.add(profile)

    profile.sex = payload.sex.value
    profile.birth_date = payload.birth_date
    profile.height_cm = payload.height_cm
    profile.activity_level = payload.activity_level.value
    profile.goal = payload.goal.value
    profile.target_weight_kg = payload.target_weight_kg
    profile.timezone = payload.timezone
    if profile.onboarding_completed_at is None:
        profile.onboarding_completed_at = datetime.now(UTC)

    await _record_weight(session, user.id, payload.weight_kg, today)
    await session.commit()
    await session.refresh(profile)

    logger.info("Profile saved for user %s", user.id)
    return ProfileWithTargets(
        profile=ProfileRead.model_validate(profile),
        current_weight_kg=payload.weight_kg,
        targets=_targets_for(profile, payload.weight_kg),
    )


async def _record_weight(
    session: AsyncSession, user_id: uuid.UUID, weight_kg: float, on_date: date
) -> None:
    """Insert today's weight, or replace it if one already exists.

    A native upsert rather than select-then-insert: the two-step version has a
    race where two requests both see no row and both insert, and the unique
    constraint turns that into a 500. ON CONFLICT makes it one atomic statement.
    """
    statement = (
        pg_insert(WeightEntry)
        .values(user_id=user_id, weight_kg=weight_kg, recorded_on=on_date)
        .on_conflict_do_update(
            constraint="uq_weight_entry_per_day",
            set_={"weight_kg": weight_kg},
        )
    )
    await session.execute(statement)


@router.post(
    "/weight",
    response_model=WeightEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log today's weight",
)
async def log_weight(
    payload: WeightEntryInput, user: CurrentUser, session: SessionDep
) -> WeightEntryRead:
    profile = await session.get(UserProfile, user.id)
    if profile is None:
        raise PROFILE_REQUIRED

    on_date = payload.recorded_on or local_today(profile.timezone)
    if on_date > local_today(profile.timezone):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot log a weight for a future date.",
        )

    await _record_weight(session, user.id, payload.weight_kg, on_date)
    await session.commit()

    result = await session.execute(
        select(WeightEntry).where(
            WeightEntry.user_id == user.id, WeightEntry.recorded_on == on_date
        )
    )
    return WeightEntryRead.model_validate(result.scalar_one())


@router.get("/weight", response_model=list[WeightEntryRead], summary="Weight history")
async def list_weights(
    user: CurrentUser, session: SessionDep, limit: int = 180
) -> list[WeightEntryRead]:
    result = await session.execute(
        select(WeightEntry)
        .where(WeightEntry.user_id == user.id)
        .order_by(WeightEntry.recorded_on.desc())
        .limit(min(limit, 730))
    )
    return [WeightEntryRead.model_validate(entry) for entry in result.scalars()]
