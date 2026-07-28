"""The curated food catalogue: browse it, and log from it."""

import logging
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import local_today
from app.core.deps import CurrentUser
from app.db.models.diary import DiaryEntry, MealSlot
from app.db.models.profile import UserProfile
from app.db.session import get_session
from app.schemas.catalogue import CatalogueFood, CatalogueResponse
from app.schemas.diary import DiaryEntryRead
from app.services.catalogue import (
    format_amount,
    get_catalogue_food,
    grams_for,
    list_catalogue,
    materialise,
    nutrients_for,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/catalogue", tags=["catalogue"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: Slugs are our own identifiers, not user text, so the pattern is a tight
#: whitelist. It also keeps a slug out of Mongo's query operators — `{"slug":
#: {"$ne": null}}` arriving as a path parameter is the NoSQL shape of injection,
#: and a string that can only contain `[a-z0-9-]` cannot become a document.
SLUG = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]


class LogCatalogueFood(BaseModel):
    """Log a quantity of a catalogue food.

    `amount` is in the food's **own** unit — 2 for eggs, 250 for millilitres of
    milk, 150 for grams of chicken. The server converts, because the conversion
    is a fact about the food and the client is not allowed to assert facts about
    food. A client that sent grams directly would be one refactor away from
    computing them itself with the wrong density.
    """

    amount: float = Field(gt=0, le=10_000)
    meal_slot: MealSlot
    #: Which local day to file it under. Absent means the user's today; supplied
    #: only when back-filling.
    day: date | None = None


@router.get("", response_model=CatalogueResponse, summary="Browse the food catalogue")
async def browse(user: CurrentUser) -> CatalogueResponse:
    """Every curated food, grouped into sections.

    Costs no USDA budget and touches Postgres not at all: the numbers were
    verified against FoodData Central once, at seed time, and stored with the FDC
    id that produced them. Browsing is a read of our own database.
    """
    sections = await list_catalogue()
    return CatalogueResponse(
        sections=sections, total=sum(len(section.foods) for section in sections)
    )


@router.get("/{slug}", response_model=CatalogueFood, summary="One catalogue food")
async def read_food(slug: SLUG, user: CurrentUser) -> CatalogueFood:
    food = await get_catalogue_food(slug)
    if food is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That food is not in the catalogue."
        )
    return food


@router.post(
    "/{slug}/log",
    response_model=DiaryEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log a catalogue food to the diary",
)
async def log_food(
    slug: SLUG, payload: LogCatalogueFood, user: CurrentUser, session: SessionDep
) -> DiaryEntryRead:
    """Convert the amount to grams, snapshot the nutrients, write the entry.

    The entry's name records what the user actually chose — "2 × egg", "250 ml" —
    rather than the gram weight derived from it. Both are stored: the label is
    what the diary shows, the grams are what the day's totals sum.
    """
    food = await get_catalogue_food(slug)
    if food is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That food is not in the catalogue."
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

    grams = grams_for(food, payload.amount)
    row = await materialise(session, food)

    entry = DiaryEntry(
        user_id=user.id,
        local_date=entry_date,
        meal_slot=payload.meal_slot.value,
        food_id=row.id,
        quantity_grams=grams,
        food_name=f"{food.name_en} ({format_amount(food, payload.amount)})",
        food_brand=None,
        logged_at=datetime.now(UTC),
        **nutrients_for(food, grams),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    logger.info("Logged catalogue food %s (%.1f g) for user %s", slug, grams, user.id)
    return DiaryEntryRead.model_validate(entry)
