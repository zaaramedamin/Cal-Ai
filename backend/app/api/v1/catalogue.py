"""The curated food catalogue: browse it, and log from it."""

import logging
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import local_today
from app.core.deps import CurrentUser
from app.db.models.diary import DiaryEntry, MealSlot
from app.db.models.profile import UserProfile
from app.db.session import get_session
from app.schemas.catalogue import CatalogueFood, CatalogueResponse, PhotoCredit
from app.schemas.diary import DiaryEntryRead
from app.services.catalogue import (
    format_amount,
    get_catalogue_row,
    grams_for,
    list_catalogue,
    nutrients_for,
    to_catalogue_food,
)
from app.services.catalogue_photos import get_photo, list_credits

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/catalogue", tags=["catalogue"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: Slugs are our own identifiers, not user text, so the pattern is a tight
#: whitelist. Parameterised SQL makes injection a non-issue on its own; this is
#: kept because a 404 for an obviously malformed slug is cheaper and clearer
#: than a database round trip that was never going to match.
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
async def browse(user: CurrentUser, session: SessionDep) -> CatalogueResponse:
    """Every curated food, grouped into sections.

    Costs no USDA budget: the numbers were verified against FoodData Central
    once, at seed time, and stored with the FDC id that produced them. Browsing
    is a read of our own database.
    """
    sections = await list_catalogue(session)
    return CatalogueResponse(
        sections=sections, total=sum(len(section.foods) for section in sections)
    )


@router.get(
    "/photo-credits",
    response_model=list[PhotoCredit],
    summary="Who took the catalogue photographs",
)
async def read_photo_credits(session: SessionDep) -> list[PhotoCredit]:
    """The attribution list the CC BY-SA licences require.

    Declared **before** `/photos/{name}` and `/{slug}` on purpose. FastAPI matches
    routes in definition order, so a literal path registered after a parameterised
    one that could swallow it is unreachable — `/photo-credits` would arrive as
    `slug="photo-credits"` and 404.
    """
    rows = await list_credits(session)
    return [
        PhotoCredit(
            slug=slug,
            name_en=name,
            attribution=attribution,
            license=licence or "",
            source_url=source_url,
        )
        for slug, name, attribution, licence, source_url in rows
    ]


@router.get(
    "/photos/{name}",
    summary="A catalogue food's photo",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def read_photo(
    name: Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9-]{0,63}-[0-9a-f]{8}\.jpg$")],
    session: SessionDep,
) -> Response:
    """Serve a stored thumbnail.

    **Unauthenticated, deliberately.** `<Image>` in React Native does not carry
    our auth header, so an authenticated image URL would need either a signed
    token per photo or a custom image component — real complexity to protect a
    picture of a banana that is identical for every user.

    Cached for a year because the URL is immutable: the filename embeds a hash of
    the bytes, so a new photo is a new URL and a stale cache is impossible. That
    is the whole reason for hashing the name rather than serving `/photos/egg`.
    """
    photo = await get_photo(session, name)
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such photo.")

    return Response(
        content=photo.data,
        media_type=photo.content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/{slug}", response_model=CatalogueFood, summary="One catalogue food")
async def read_food(slug: SLUG, user: CurrentUser, session: SessionDep) -> CatalogueFood:
    row = await get_catalogue_row(session, slug)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That food is not in the catalogue."
        )
    return to_catalogue_food(row)


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
    row = await get_catalogue_row(session, slug)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That food is not in the catalogue."
        )
    food = to_catalogue_food(row)

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
