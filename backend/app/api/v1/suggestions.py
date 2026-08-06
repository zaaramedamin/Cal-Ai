"""What to eat next, given what you have eaten today.

The candidate pool is the user's own staples first, then the curated popular
list. Both are already in the food cache with real USDA numbers, so a suggestion
is arithmetic over measured values — see `services/suggestions.py` for why no
model is involved.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.profile import _latest_weight, _targets_for
from app.core.dates import local_today
from app.core.deps import CurrentUser
from app.db.models.diary import DiaryEntry
from app.db.models.food import Food, FoodSource
from app.db.models.profile import UserProfile
from app.db.session import get_session
from app.schemas.food import FoodSearchResult
from app.services.food_cache import search_local
from app.services.popular_foods import POPULAR_FOODS
from app.services.suggestions import Gap, suggest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/suggestions", tags=["suggestions"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: How many curated foods to pull into the candidate pool. The whole list would
#: mean sixty local searches per request for no gain — the ranking only ever
#: returns a handful, and the user's own foods are better candidates anyway.
CURATED_SAMPLE = 24


class SuggestionRead(BaseModel):
    food: FoodSearchResult
    #: The portion being suggested, already sized to the remaining budget.
    grams: float
    kcal: float
    #: Why this was suggested, in the user's own numbers. A recommendation
    #: without a stated reason is indistinguishable from an advertisement.
    reason: str


class SuggestionsResponse(BaseModel):
    suggestions: list[SuggestionRead]
    remaining_kcal: float
    remaining_protein_g: float
    remaining_carbs_g: float
    remaining_fat_g: float
    #: Set when there is deliberately nothing to suggest, so the app can explain
    #: itself rather than showing an unexplained empty card.
    note: str | None = None


@router.get("", response_model=SuggestionsResponse, summary="What to eat next")
async def read_suggestions(user: CurrentUser, session: SessionDep) -> SuggestionsResponse:
    """Rank real foods against the calories and macros left in the day.

    Returns an empty list when the honest answer is "nothing" — the day is
    already full, or nothing in the pool fits. A suggestions panel that always
    finds something to recommend eventually recommends nonsense, and the `note`
    field exists so the app can say which of the two happened.
    """
    profile = await session.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Complete onboarding first."
        )

    weight = await _latest_weight(session, user.id)
    if weight is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Log a weight first."
        )

    targets = _targets_for(profile, float(weight.weight_kg))
    today = local_today(profile.timezone)

    eaten = await session.execute(
        select(
            func.coalesce(func.sum(DiaryEntry.kcal), 0),
            func.coalesce(func.sum(DiaryEntry.protein_g), 0),
            func.coalesce(func.sum(DiaryEntry.carbs_g), 0),
            func.coalesce(func.sum(DiaryEntry.fat_g), 0),
        ).where(DiaryEntry.user_id == user.id, DiaryEntry.local_date == today)
    )
    kcal, protein, carbs, fat = (float(value) for value in eaten.one())

    gap = Gap(
        kcal=targets.calories - kcal,
        protein_g=targets.macros.protein_g - protein,
        carbs_g=targets.macros.carbs_g - carbs,
        fat_g=targets.macros.fat_g - fat,
    )

    response = SuggestionsResponse(
        suggestions=[],
        remaining_kcal=round(gap.kcal, 1),
        remaining_protein_g=round(gap.protein_g, 1),
        remaining_carbs_g=round(gap.carbs_g, 1),
        remaining_fat_g=round(gap.fat_g, 1),
    )

    if not gap.has_room:
        response.note = (
            "You've hit your calories for today. Nothing to suggest — that's the goal."
            if gap.kcal >= 0
            else "You're over your calorie target for today, so there's nothing to suggest."
        )
        return response

    candidates = await _candidate_foods(session, user.id)
    ranked = suggest(candidates, gap)

    if not ranked:
        response.note = (
            "Nothing in your usual foods fits what's left of today. "
            "Try a search — the numbers still come from USDA."
        )
        return response

    response.suggestions = [
        SuggestionRead(
            food=FoodSearchResult.model_validate(item.food),
            grams=item.grams,
            kcal=item.kcal,
            reason=item.reason,
        )
        for item in ranked
    ]
    return response


async def _candidate_foods(session: AsyncSession, user_id) -> list[Food]:
    """The user's own foods first, then a sample of the curated list.

    Ordering matters: a suggestion the user has eaten before is one they will
    actually act on, while a technically-optimal food they have never chosen is
    advice they will scroll past. Their history goes in first so it wins ties.

    AI-estimated foods are excluded. Recommending a guessed number would be a
    strange thing to do with a feature whose entire value is that the numbers
    are checkable.
    """
    own = await session.execute(
        select(Food)
        .join(DiaryEntry, DiaryEntry.food_id == Food.id)
        .where(DiaryEntry.user_id == user_id, Food.source != FoodSource.AI_ESTIMATE)
        .group_by(Food.id)
        .order_by(func.count().desc())
        .limit(20)
    )
    candidates = list(own.scalars())
    seen = {food.id for food in candidates}

    # Only the cache is consulted for the curated foods — no USDA calls. A
    # suggestions panel must not be able to spend the shared upstream budget,
    # since it renders on a screen the user did not ask a question on.
    for entry in POPULAR_FOODS[:CURATED_SAMPLE]:
        for food in await search_local(session, entry.search_term, 3, user_id):
            if food.id in seen or not _is_plausible_match(entry.search_term, food.name):
                continue
            seen.add(food.id)
            candidates.append(food)
            break

    return candidates


def _is_plausible_match(search_term: str, food_name: str) -> bool:
    """Guard against the cache offering something that merely shares a word.

    Searching "rice white cooked" against a sparse cache happily returned "Rice
    flour, brown" — it contains "rice", so it scores. For a *search* that is a
    tolerable near-miss the user can scroll past. For a *suggestion* it is not:
    the app is asserting this is a good idea, and 305 g of rice flour is not.

    The rule is that the food's opening word — which is the food itself in USDA's
    naming, "Rice, white, cooked" — must be one of the words being searched for.
    A dish that mentions the ingredient later fails, which is the intent.
    """
    head = food_name.lower().strip().split(",")[0].split()
    if not head:
        return False
    wanted = set(search_term.lower().split())
    # Singular/plural: USDA writes "Bananas, raw" for a search of "banana".
    return any(word.rstrip("s") in {term.rstrip("s") for term in wanted} for word in head)
