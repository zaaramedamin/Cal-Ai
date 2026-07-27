"""Meal photo scanning.

The endpoint is a two-stage pipeline, and the split is the whole point:

1. Gemini looks at the photo and answers *what* and *how much* — food names and
   gram estimates, never nutrition.
2. Each name is matched against the USDA-backed food cache, which is where every
   calorie and macro in the response comes from.

So a scan cannot introduce an invented nutrition value even if the model
hallucinates wildly: the worst case is a wrong food name, which the user sees
and corrects on the review screen before anything is logged.
"""

import base64
import binascii
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.rate_limit import RateLimit
from app.db.models.food import Food, FoodSource
from app.db.session import get_session
from app.schemas.food import FoodSearchResult
from app.schemas.scan import ScannedItem, ScanRequest, ScanResponse
from app.services.food_cache import search_foods, upsert_estimated_food
from app.services.vision import (
    VisionClient,
    VisionItem,
    VisionNotConfigured,
    VisionQuotaExhausted,
    VisionUnavailable,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scan", tags=["scan"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: Tighter than food search, because each scan spends from two shared budgets:
#: the Gemini free tier (~250 requests a day for the whole deployment) and,
#: through the matching step, the USDA hourly allowance. Twenty an hour is far
#: more than anyone photographs meals and still leaves room for other users.
scan_rate_limit = RateLimit(times=20, seconds=3600, scope="scan")

#: How many candidates to pull per detected item. We only use the first, but
#: asking for a few makes the local-cache ordering meaningful.
MATCH_CANDIDATES = 5


def get_vision_client() -> VisionClient:
    """Injectable so tests can substitute a fake without touching the network."""
    return VisionClient()


VisionDep = Annotated[VisionClient, Depends(get_vision_client)]


@router.post(
    "",
    response_model=ScanResponse,
    summary="Identify foods in a meal photo",
    dependencies=[Depends(scan_rate_limit)],
)
async def scan_meal(
    payload: ScanRequest,
    user: CurrentUser,
    session: SessionDep,
    vision: VisionDep,
) -> ScanResponse:
    """Analyse a photo and return detected foods matched to real nutrition data.

    The photo is held in memory for the duration of the request and never
    written to disk or to the database. Nothing about the image is retained.
    """
    # Validate the encoding here rather than letting Gemini reject it: a local
    # 422 costs nothing, while a round trip to spend quota on malformed bytes
    # costs part of a shared daily budget.
    try:
        base64.b64decode(payload.image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="image_base64 is not valid base64.",
        ) from exc

    try:
        result = await vision.analyse_meal(payload.image_base64, payload.media_type)
    except VisionNotConfigured as exc:
        # 503 rather than 500: the server is fine, this one feature is switched
        # off, and the message tells the operator exactly how to switch it on.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Photo scanning is not configured on this server. "
                "Set GEMINI_API_KEY — a free key takes a minute at "
                "https://aistudio.google.com/apikey"
            ),
        ) from exc
    except VisionQuotaExhausted as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The daily photo-scanning allowance is used up. Try again later.",
            # An hour is a guess — Gemini's free tier resets per minute for rate
            # and per day for volume, and the 429 does not say which was hit.
            # Erring long is kinder than telling the user to retry into a wall.
            headers={"Retry-After": "3600"},
        ) from exc
    except VisionUnavailable as exc:
        logger.warning("Vision analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not analyse the photo right now. Try again in a moment.",
        ) from exc

    # Sequential, not gathered. One AsyncSession is not safe for concurrent use,
    # and a fan-out of eight simultaneous USDA calls would spike a shared budget
    # we are trying to spend carefully. Eight cache lookups are fast anyway.
    matches: dict[int, Food | None] = {}
    for index, detected in enumerate(result.items):
        # `query` is the model's stripped-down search term ("chicken breast"),
        # not the descriptive name it shows the user ("grilled chicken breast").
        # Food databases file things formally and the descriptive form rarely
        # matches; the bare noun usually does.
        foods, _ = await search_foods(session, detected.query, limit=MATCH_CANDIDATES)
        matches[index] = foods[0] if foods else None

    # Everything above is measured data. Below this line is the one exception,
    # and it only runs for foods the databases genuinely could not identify.
    missing = [index for index, food in matches.items() if food is None]
    if missing:
        matches |= await _estimate_missing(session, vision, result.items, missing)

    items = [
        ScannedItem(
            detected_name=detected.name,
            estimated_grams=detected.quantity_grams,
            confidence=detected.confidence,
            match=(
                FoodSearchResult.model_validate(matches[index]) if matches[index] else None
            ),
        )
        for index, detected in enumerate(result.items)
    ]

    unmatched = sum(1 for item in items if item.match is None)
    estimated = sum(
        1 for item in items if item.match and item.match.source == FoodSource.AI_ESTIMATE
    )
    logger.info(
        "Scan for user %s: %d detected, %d AI-estimated, %d unmatched",
        user.id,
        len(items),
        estimated,
        unmatched,
    )

    return ScanResponse(
        items=items,
        notes=result.notes,
        unmatched_count=unmatched,
        estimated_count=estimated,
    )


async def _estimate_missing(
    session: AsyncSession,
    vision: VisionClient,
    detected: list[VisionItem],
    missing: list[int],
) -> dict[int, Food | None]:
    """Last resort for foods no database could match.

    Asks the model for per-100 g nutrition and stores it under
    `FoodSource.AI_ESTIMATE` — the only rows in this database whose numbers were
    not measured. They are excluded from food search, so they surface nowhere
    except the scan that produced them, and the app labels them wherever they
    appear.

    A failure here is not an error. The items simply stay unmatched, which is
    the state the app already handles by offering a manual search.
    """
    names = [detected[index].name for index in missing]
    try:
        estimates = await vision.estimate_nutrition(names)
    except (VisionUnavailable, VisionQuotaExhausted, VisionNotConfigured) as exc:
        logger.info("Nutrition estimation unavailable, leaving %d unmatched: %s", len(names), exc)
        return {}

    resolved: dict[int, Food | None] = {}
    for index in missing:
        estimate = estimates.get(detected[index].name.strip().lower())
        if estimate is None:
            continue
        resolved[index] = await upsert_estimated_food(session, estimate)

    if resolved:
        await session.commit()
    return resolved
