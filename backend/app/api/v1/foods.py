"""Food search and detail."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser
from app.core.rate_limit import RateLimit
from app.db.models.food import Food
from app.db.session import get_session
from app.schemas.food import FoodRead, FoodSearchResponse, FoodSearchResult
from app.services.food_cache import search_foods

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
