"""Caching layer between the API and USDA.

The cache is not an optimisation bolted on afterwards — it is what makes the
integration viable at all. USDA allows 1,000 requests an hour for the whole
deployment, so every search that can be answered from Postgres is a search that
does not spend part of a shared, finite budget.
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Integer, case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.food import Food, FoodPortion, FoodSource
from app.services.usda import UnusableFood, UsdaClient, UsdaUnavailable, normalise_food

logger = logging.getLogger(__name__)

#: Below this many local hits we ask USDA as well. A search returning three
#: cached foods is probably missing better matches; one returning twenty is not.
LOCAL_RESULT_THRESHOLD = 8

#: Words that carry no matching signal. Deliberately tiny — it holds only
#: grammatical filler, not cooking methods. "raw", "cooked" and "roasted" all
#: appear in real USDA names ("Bananas, raw"), so dropping them would throw away
#: signal; the scoring below already tolerates a token that fails to match.
NOISE_WORDS = frozenset({"a", "an", "the", "of", "with", "and", "in", "on", "or"})

_WORD = re.compile(r"[a-z0-9]+")


def tokenise(query: str) -> list[str]:
    """Split a search phrase into scoreable words, longest-first.

    Longest-first because the ordering shows up in logs and explains ranking:
    the distinctive word in "grilled chicken breast" is "chicken", not "grilled".
    """
    words = [w for w in _WORD.findall(query.lower()) if w not in NOISE_WORDS and len(w) > 1]
    return sorted(set(words), key=len, reverse=True)[:6]


async def search_local(session: AsyncSession, query: str, limit: int) -> list[Food]:
    """Search cached foods, ranked by how many query words a name contains.

    **Why not a single ILIKE on the whole phrase, which is what this used to do.**

    USDA names are formal and comma-ordered: a grilled chicken breast is
    "Chicken, broilers or fryers, breast, meat only, cooked, roasted". The phrase
    "grilled chicken breast" appears nowhere inside it, so a substring match
    returns nothing — while a name that happens to *contain* the literal phrase
    wins even when it is wrong. Searching "olive oil" that way returned
    "Mayonnaise, reduced fat, with olive oil" and never the actual cooking oil.

    Scoring per word fixes both halves. A name matching more query words ranks
    higher; ties break on brevity, because "Oil, olive, salad or cooking" is a
    better answer for "olive oil" than any longer name that also mentions it.
    """
    tokens = tokenise(query)
    if not tokens:
        return []

    # Two points per query word present anywhere, plus three if the name *opens*
    # with one. That second signal matters because USDA writes names head-noun
    # first — "Oil, olive, salad or cooking", "Bananas, raw" — so a name starting
    # with a query word is usually the food itself, while one that merely
    # mentions it later is usually a dish containing it. Without the bonus,
    # "Mayonnaise, reduced fat, with olive oil" ties with the actual olive oil.
    # Built as SQL via `case` so ranking happens in Postgres rather than by
    # pulling every candidate row back to compare in Python.
    matches = (
        case((Food.name.ilike(f"%{_escape_like(token)}%"), 2), else_=0) for token in tokens
    )
    heads = (
        case((Food.name.ilike(f"{_escape_like(token)}%"), 3), else_=0) for token in tokens
    )
    score = sum([*matches, *heads], start=func.cast(0, Integer))

    result = await session.execute(
        select(Food)
        # AI estimates are never returned by a search. They exist only so a
        # scanned food the databases could not identify still has a row to log
        # against, and they must not leak into a normal food search where the
        # user would have no idea the numbers were not measured.
        .where(Food.source != FoodSource.AI_ESTIMATE)
        .where(score > 0)
        .order_by(score.desc(), func.length(Food.name), Food.name)
        .limit(limit)
    )
    return list(result.scalars())


def _escape_like(token: str) -> str:
    """Neutralise LIKE wildcards inside a user-supplied word.

    A search for "100%" would otherwise become a wildcard and match everything.
    """
    return token.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


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


async def upsert_estimated_food(session: AsyncSession, estimate: Any) -> Food:
    """Store an AI-estimated food, keyed so repeats reuse one row.

    `source_id` is a slug of the name rather than a random id, so scanning
    "shakshuka" on Tuesday and again on Friday updates one row instead of
    littering the table with duplicates that all say the same thing.

    Deliberately does not commit. The caller decides the transaction boundary,
    which matters because several of these are written in one request.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", estimate.name.strip().lower()).strip("-")[:64]
    return await upsert_food(
        session,
        {
            "source": FoodSource.AI_ESTIMATE,
            "source_id": slug or "unnamed",
            "name": estimate.name.strip(),
            "brand": None,
            "kcal": estimate.kcal,
            "protein_g": estimate.protein_g,
            "carbs_g": estimate.carbs_g,
            "fat_g": estimate.fat_g,
            "fibre_g": estimate.fibre_g,
            "sugars_g": estimate.sugars_g,
            # Never guessed. The model is asked for these only when confident,
            # and a missing one stays NULL so the app shows an em dash exactly
            # as it does for a USDA gap.
            "saturated_fat_g": None,
            "sodium_mg": None,
            "portions": [],
        },
    )


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

    fetched: list[Food] = []
    for payload in payloads:
        try:
            fetched.append(await upsert_food(session, normalise_food(payload)))
        except UnusableFood as exc:
            # Expected and routine: plenty of USDA rows lack the nutrients we
            # need. Skipping them is the rule working, not a failure.
            logger.debug("Skipping unusable USDA food: %s", exc)

    await session.commit()
    logger.info("Cached %d/%d USDA foods for %r", len(fetched), len(payloads), query)

    # Return what USDA just gave us, in USDA's own relevance order, rather than
    # re-querying the cache. Re-querying was a real bug: we would fetch exactly
    # the right food, store it, then fail to find it again because our own text
    # match could not connect "grilled chicken breast" to the formal name USDA
    # files it under. USDA's relevance ranking is better than ours and it is
    # already sitting in the response — throwing it away was pure loss.
    merged = list(fetched)
    seen = {food.id for food in merged}
    merged.extend(food for food in local if food.id not in seen)
    return merged[:limit], False
