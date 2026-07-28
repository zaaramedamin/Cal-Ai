"""Food search and detail."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser
from app.core.rate_limit import RateLimit
from app.db.models.diary import DiaryEntry
from app.db.models.food import Food
from app.db.session import get_session
from app.schemas.food import (
    FoodRead,
    FoodSearchResponse,
    FoodSearchResult,
    PopularFoodRead,
    QuickAddFood,
)
from app.services.food_cache import search_foods
from app.services.popular_foods import POPULAR_FOODS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/foods", tags=["foods"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: Search is the one endpoint that can spend our shared USDA budget, so it gets
#: its own limit. Generous enough for real typing behind a debounce, tight enough
#: that one client cannot drain the hourly allowance for everybody.
search_rate_limit = RateLimit(times=120, seconds=3600, scope="food-search")


@router.get(
    "/search",
    response_model=FoodSearchResponse,
    summary="Search foods",
    dependencies=[Depends(search_rate_limit)],
)
async def search(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[str, Query(min_length=2, max_length=64, description="Search text")],
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
) -> FoodSearchResponse:
    """Search the cache, topping up from USDA when results are thin.

    Requires authentication even though food data is not personal. The endpoint
    spends a shared, finite upstream budget, and an unauthenticated one would let
    anybody exhaust it for every user.

    A minimum of two characters is not arbitrary: single-letter searches match
    thousands of cached rows and tell the user nothing.
    """
    foods, upstream_unavailable = await search_foods(session, q, limit=limit)

    return FoodSearchResponse(
        query=q,
        results=[FoodSearchResult.model_validate(food) for food in foods],
        upstream_unavailable=upstream_unavailable,
    )


#: How far back "what I usually eat" looks. Long enough to catch a weekly
#: staple, short enough that a food abandoned two months ago stops being offered.
QUICK_ADD_WINDOW_DAYS = 60


@router.get(
    "/quick-add",
    response_model=list[QuickAddFood],
    summary="Foods this user logs often, ready to re-log in one tap",
)
async def quick_add(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> list[QuickAddFood]:
    """The user's own staples, with the quantity they last used.

    **Why the last quantity is part of the answer.** Logging porridge again is
    only one tap if the app already knows it was 60 g — otherwise the chip just
    opens the portion screen and has saved nothing. The most common act in a
    food tracker is repeating yesterday, and this endpoint exists to make that
    act cost one tap instead of six.

    Ordered by how often the food is logged, ties broken by recency, so the
    result reads as "your usuals" rather than "your history". Frequency is the
    better signal: the last thing eaten is often the unusual thing.

    Declared above `/{food_id}` deliberately — FastAPI matches routes in
    definition order, and the parameterised route would otherwise swallow
    "quick-add" and try to parse it as a UUID.
    """
    cutoff = datetime.now(UTC) - timedelta(days=QUICK_ADD_WINDOW_DAYS)

    # One pass with window functions rather than a group-by followed by a second
    # query for each food's latest entry. `row_number` picks the most recent row
    # per food; `count` over the same partition counts them all.
    ranked = (
        select(
            DiaryEntry.food_id.label("food_id"),
            DiaryEntry.quantity_grams.label("quantity_grams"),
            DiaryEntry.meal_slot.label("meal_slot"),
            DiaryEntry.logged_at.label("logged_at"),
            func.count().over(partition_by=DiaryEntry.food_id).label("times_logged"),
            func.row_number()
            .over(partition_by=DiaryEntry.food_id, order_by=DiaryEntry.logged_at.desc())
            .label("rank"),
        )
        .where(
            DiaryEntry.user_id == user.id,
            # Recipe entries have no food_id and cannot be re-logged this way;
            # they have their own screen.
            DiaryEntry.food_id.is_not(None),
            DiaryEntry.logged_at >= cutoff,
        )
        .subquery()
    )

    result = await session.execute(
        select(Food, ranked.c.quantity_grams, ranked.c.meal_slot, ranked.c.times_logged)
        .join(ranked, Food.id == ranked.c.food_id)
        .where(ranked.c.rank == 1)
        .order_by(ranked.c.times_logged.desc(), ranked.c.logged_at.desc())
        .limit(limit)
    )

    return [
        QuickAddFood(
            id=food.id,
            source=food.source,
            name=food.name,
            brand=food.brand,
            kcal=food.kcal,
            protein_g=food.protein_g,
            carbs_g=food.carbs_g,
            fat_g=food.fat_g,
            last_quantity_grams=float(quantity),
            last_meal_slot=slot,
            times_logged=times,
        )
        for food, quantity, slot, times in result
    ]


@router.get(
    "/popular",
    response_model=list[PopularFoodRead],
    summary="A short curated list of foods people actually log",
)
async def popular(user: CurrentUser) -> list[PopularFoodRead]:
    """The browse menu: short names and emoji, grouped into sections.

    Static and free — no database work, no upstream call — because it is a menu
    rather than data. The nutrition still comes from USDA: each entry carries the
    `search_term` that finds the authoritative row, and the app resolves it when
    the user taps.

    Requires auth only for consistency with the rest of the food routes; there is
    nothing sensitive here.
    """
    return [
        PopularFoodRead(
            name=food.name,
            emoji=food.emoji,
            search_term=food.search_term,
            category=food.category,
        )
        for food in POPULAR_FOODS
    ]


@router.get("/{food_id}", response_model=FoodRead, summary="Food detail with portions")
async def read_food(food_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> FoodRead:
    """Full nutrients and every friendly portion.

    `selectinload` on portions rather than a lazy relationship: under asyncio a
    lazy load fires outside an await and raises MissingGreenlet, which surfaces
    as a baffling error far from its cause.
    """
    result = await session.execute(
        select(Food).where(Food.id == food_id).options(selectinload(Food.portions))
    )
    food = result.scalar_one_or_none()
    if food is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Food not found.")

    return FoodRead.model_validate(food)
