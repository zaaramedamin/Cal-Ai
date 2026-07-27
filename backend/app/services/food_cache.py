"""Caching layer between the API and USDA.

The cache is not an optimisation bolted on afterwards — it is what makes the
integration viable at all. USDA allows 1,000 requests an hour for the whole
deployment, so every search that can be answered from Postgres is a search that
does not spend part of a shared, finite budget.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.food import Food, FoodPortion
from app.services.usda import UnusableFood, UsdaClient, UsdaUnavailable, normalise_food

logger = logging.getLogger(__name__)

#: Below this many local hits we ask USDA as well. A search returning three
#: cached foods is probably missing better matches; one returning twenty is not.
LOCAL_RESULT_THRESHOLD = 8


async def search_local(session: AsyncSession, query: str, limit: int) -> list[Food]:
    """Search cached foods by name.

    ILIKE rather than Postgres full-text search. Full-text stems and drops stop
    words, which is right for prose and wrong for food names — searching "oat"
    should match "oat milk", and a tsquery for "oats" would not match "oat".
    A trigram index is the proper upgrade when the cache is large enough for this
    to be slow; it is not yet, and pretending otherwise would be premature.
    """
    pattern = f"%{query.strip()}%"
    result = await session.execute(
        select(Food)
        .where(Food.name.ilike(pattern))
        # Shorter names first: "Banana, raw" is a better match for "banana" than
        # "Banana bread, prepared from recipe, with nuts".
        .order_by(func.length(Food.name), Food.name)
        .limit(limit)
    )
    return list(result.scalars())


async def upsert_food(session: AsyncSession, normalised: dict[str, Any]) -> Food:
    """Insert or refresh one normalised food, with its portions.

    ON CONFLICT on (source, source_id) rather than select-then-insert: two
    concurrent searches for the same term would otherwise both find nothing and
    both insert, and the unique constraint would turn that into a 500.
    """
    portions = normalised.pop("portions", [])
    normalised["data_fetched_at"] = datetime.now(UTC)

    statement = (
        pg_insert(Food)
        .values(**normalised)
        .on_conflict_do_update(
            constraint="uq_food_source_id",
            set_={
                key: normalised[key]
                for key in (
                    "name",
                    "brand",
                    "kcal",
                    "protein_g",
                    "carbs_g",
                    "fat_g",
                    "sugars_g",
                    "saturated_fat_g",
                    "fibre_g",
                    "sodium_mg",
                    "data_fetched_at",
                )
            },
        )
        .returning(Food.id)
    )
    food_id = (await session.execute(statement)).scalar_one()

    if portions:
        existing = await session.execute(
            select(func.count()).select_from(FoodPortion).where(FoodPortion.food_id == food_id)
        )
        # Only seed portions the first time. Re-adding on every refresh would
        # accumulate duplicates of "1 medium banana" without bound.
        if existing.scalar_one() == 0:
            for index, portion in enumerate(portions):
                session.add(
                    FoodPortion(
                        food_id=food_id,
                        label=portion["label"],
                        grams=portion["grams"],
                        is_default=index == 0,
                    )
                )

    return (await session.execute(select(Food).where(Food.id == food_id))).scalar_one()


async def search_foods(
    session: AsyncSession, query: str, *, limit: int, client: UsdaClient | None = None
) -> tuple[list[Food], bool]:
    """Search the cache, topping up from USDA when thin.

    Returns the foods and whether upstream was unavailable, so the app can tell
    the user "these are cached results" instead of silently showing a short list
    as though it were complete.
    """
    local = await search_local(session, query, limit)
    if len(local) >= LOCAL_RESULT_THRESHOLD:
        return local, False

    usda = client or UsdaClient()
    try:
        payloads = await usda.search(query, page_size=limit)
    except UsdaUnavailable:
        logger.warning("USDA unavailable; serving %d cached results for %r", len(local), query)
        return local, True

    stored = 0
    for payload in payloads:
        try:
            await upsert_food(session, normalise_food(payload))
            stored += 1
        except UnusableFood as exc:
            # Expected and routine: plenty of USDA rows lack the nutrients we
            # need. Skipping them is the rule working, not a failure.
            logger.debug("Skipping unusable USDA food: %s", exc)

    await session.commit()
    logger.info("Cached %d/%d USDA foods for %r", stored, len(payloads), query)

    return await search_local(session, query, limit), False
