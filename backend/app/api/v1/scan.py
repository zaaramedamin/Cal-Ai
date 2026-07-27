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
from app.db.session import get_session
from app.schemas.food import FoodSearchResult
from app.schemas.scan import ScannedItem, ScanRequest, ScanResponse
from app.services.food_cache import search_foods
from app.services.vision import (
    VisionClient,
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

    items: list[ScannedItem] = []
    unmatched = 0

    # Sequential, not gathered. One AsyncSession is not safe for concurrent use,
    # and a fan-out of eight simultaneous USDA calls would spike a shared budget
    # we are trying to spend carefully. Eight cache lookups are fast anyway.
    for detected in result.items:
        foods, _ = await search_foods(session, detected.name, limit=MATCH_CANDIDATES)
        best = foods[0] if foods else None
        if best is None:
            unmatched += 1

        items.append(
            ScannedItem(
                detected_name=detected.name,
                estimated_grams=detected.quantity_grams,
                confidence=detected.confidence,
                match=FoodSearchResult.model_validate(best) if best else None,
            )
        )

    logger.info("Scan for user %s: %d detected, %d unmatched", user.id, len(items), unmatched)

    return ScanResponse(items=items, notes=result.notes, unmatched_count=unmatched)
