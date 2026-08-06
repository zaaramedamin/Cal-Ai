"""Food search and detail."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser
from app.core.rate_limit import RateLimit
from app.db.models.diary import DiaryEntry
from app.db.models.food import Food, FoodKind, FoodPortion, FoodSource, UnitKind
from app.db.session import get_session
from app.schemas.food import (
    CustomFoodInput,
    FoodRead,
    FoodSearchResponse,
    FoodSearchResult,
    PopularFoodRead,
    QuickAddFood,
)
from app.services.food_cache import browse_search, readable_name, upsert_food
from app.services.openfoodfacts import (
    OffClient,
    OffUnavailable,
    ProductNotFound,
    UnusableProduct,
)
from app.services.popular_foods import POPULAR_FOODS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/foods", tags=["foods"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: Search is the one endpoint that can spend our shared USDA budget, so it gets
#: its own limit. Generous enough for real typing behind a debounce, tight enough
#: that one client cannot drain the hourly allowance for everybody.
search_rate_limit = RateLimit(times=120, seconds=3600, scope="food-search")

#: Barcode lookups hit Open Food Facts, who ask clients to be reasonable and
#: rate-limit those that are not. Tighter than search because a scan is one
#: deliberate act, not a keystroke behind a debounce.
barcode_rate_limit = RateLimit(times=60, seconds=3600, scope="barcode")

#: How many results a search returns by default.
#:
#: Was 25, which is a scrollable wall when most of it is USDA laboratory names.
#: Six is enough to hold the varieties somebody genuinely chooses between — the
#: Tunisian table alone has four kinds of bread — while staying a *choice*
#: rather than a list to read. The client can still ask for more.
BROWSE_LIMIT = 6


def get_off_client() -> OffClient:
    """Overridable in tests, so no test ever calls Open Food Facts for real."""
    return OffClient()


OffDep = Annotated[OffClient, Depends(get_off_client)]


@router.get(
    "/barcode/{barcode}",
    response_model=FoodRead,
    summary="Look up a packaged food by its barcode",
    dependencies=[Depends(barcode_rate_limit)],
)
async def by_barcode(
    barcode: Annotated[str, Path(pattern=r"^\d{6,14}$")],
    user: CurrentUser,
    session: SessionDep,
    off: OffDep,
    refresh: Annotated[bool, Query(description="Re-fetch even if cached")] = False,
) -> FoodRead:
    """Resolve a barcode to a food, caching it locally on the way through.

    **The cache is checked first** for speed and to be a good citizen of a free,
    donation-funded service — not, as an earlier version of this comment claimed,
    to protect diary history. It cannot affect history: `diary_entries` snapshot
    their nutrients at log time precisely so an upstream revision can never
    rewrite what someone ate. That is what makes `?refresh=true` below safe.
    """
    existing = (
        await session.execute(
            select(Food)
            .where(Food.source == "off", Food.source_id == barcode)
            .options(selectinload(Food.portions))
        )
    ).scalar_one_or_none()
    if existing is not None and not refresh:
        return FoodRead.model_validate(existing)

    try:
        normalised = await off.product(barcode)
    except ProductNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            # Says what to do next. "Not found" alone leaves the user staring at
            # a barcode that plainly exists on the tin in their hand.
            detail=(
                "That barcode is not in Open Food Facts. Search for it by name "
                "instead, or add it as your own food."
            ),
        ) from exc
    except UnusableProduct as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            # Deliberately explicit. The alternative is storing the product with
            # zeros, which would look like a working scan and put a wrong number
            # in the diary.
            detail=(
                "That product is in the database but has no nutrition recorded, "
                "so there is nothing to log. Search for it by name instead."
            ),
        ) from exc
    except OffUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach the barcode database. Try again in a moment.",
        ) from exc

    food = await upsert_food(session, normalised)
    await session.commit()

    logger.info("Barcode %s resolved to %s for user %s", barcode, food.name, user.id)

    stored = (
        await session.execute(
            select(Food).where(Food.id == food.id).options(selectinload(Food.portions))
        )
    ).scalar_one()
    return FoodRead.model_validate(stored)


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
    limit: Annotated[int, Query(ge=1, le=50)] = BROWSE_LIMIT,
) -> FoodSearchResponse:
    """Curated foods first; USDA only when nothing else matches.

    **This endpoint is a list a person reads**, which is what separates it from
    `search_foods` — the resolver photo scanning uses, where the candidates are
    never shown and only the winner's numbers matter. USDA writes names for a
    database, not for somebody logging lunch, and twenty-five of those was the
    wall of text this app is trying not to be.

    Requires authentication even though food data is not personal. The endpoint
    spends a shared, finite upstream budget, and an unauthenticated one would let
    anybody exhaust it for every user.

    A minimum of two characters is not arbitrary: single-letter searches match
    thousands of cached rows and tell the user nothing.
    """
    foods, upstream_unavailable = await browse_search(
        session, q, limit=limit, owner_id=user.id
    )

    results = []
    for food in foods:
        result = FoodSearchResult.model_validate(food)
        # Only the fallback rows are renamed, and only for display. Nothing that
        # came from the catalogue, the Tunisian table or a person is touched —
        # those names were written by somebody for this purpose already.
        if food.source in (FoodSource.USDA, FoodSource.OFF):
            result.name = readable_name(result.name)
        results.append(result)

    return FoodSearchResponse(
        query=q,
        results=results,
        upstream_unavailable=upstream_unavailable,
    )


#: How far back "what I usually eat" looks. Long enough to catch a weekly
#: staple, short enough that a food abandoned two months ago stops being offered.
QUICK_ADD_WINDOW_DAYS = 60


@router.post(
    "",
    response_model=FoodRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a food from a label",
)
async def create_custom_food(
    payload: CustomFoodInput,
    user: CurrentUser,
    session: SessionDep,
) -> FoodRead:
    """Store a food the user entered themselves.

    **Owned, not shared.** `owner_id` is set, so this food belongs to the person
    who typed it and never appears in anybody else's search. That is the whole
    difference between this and the catalogue: USDA figures are measured and
    shared, these are one person's reading of one label, and promoting them to
    everybody would quietly turn a private note into a claim about the world.

    A barcode makes the entry findable by scanning again, which is the point of
    creating one after a failed scan.
    """
    food = Food(
        source=FoodSource.USER,
        # Barcode when there is one, otherwise a generated id — `source_id` is
        # part of the uniqueness key and cannot be null.
        source_id=payload.barcode or f"user:{uuid.uuid4()}",
        kind=FoodKind.CUSTOM,
        owner_id=user.id,
        name=payload.name.strip(),
        brand=payload.brand.strip() if payload.brand else None,
        is_liquid=payload.is_liquid,
        unit=UnitKind.MILLILITRES if payload.is_liquid else UnitKind.GRAMS,
        grams_per_unit=1,
        kcal=payload.kcal,
        protein_g=payload.protein_g,
        carbs_g=payload.carbs_g,
        fat_g=payload.fat_g,
        sugars_g=payload.sugars_g,
        saturated_fat_g=payload.saturated_fat_g,
        fibre_g=payload.fibre_g,
        sodium_mg=payload.sodium_mg,
        data_fetched_at=datetime.now(UTC),
    )
    session.add(food)
    await session.flush()

    if payload.serving_grams is not None:
        session.add(
            FoodPortion(
                food_id=food.id,
                label=f"1 serving ({payload.serving_grams:g} g)",
                grams=payload.serving_grams,
                is_default=True,
            )
        )

    await session.commit()
    logger.info("User %s created custom food %s", user.id, food.id)

    stored = (
        await session.execute(
            select(Food).where(Food.id == food.id).options(selectinload(Food.portions))
        )
    ).scalar_one()
    return FoodRead.model_validate(stored)


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
        # Third place a withdrawn food has to be filtered out, after search and
        # the catalogue. This one is easy to miss because the rows come from the
        # user's own history rather than from a lookup — but it is still a list
        # of one-tap suggestions, and a food we upheld a report against should
        # not be offered again. The diary entries behind it stay readable.
        .where(Food.withdrawn_at.is_(None))
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
