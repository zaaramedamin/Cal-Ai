"""Caching layer between the API and USDA.

The cache is not an optimisation bolted on afterwards — it is what makes the
integration viable at all. USDA allows 1,000 requests an hour for the whole
deployment, so every search that can be answered from Postgres is a search that
does not spend part of a shared, finite budget.
"""

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Integer, case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.food import Food, FoodKind, FoodPortion, FoodSource, ReviewStatus
from app.services.usda import UnusableFood, UsdaClient, UsdaUnavailable, normalise_food

logger = logging.getLogger(__name__)

#: Below this many local hits we ask USDA as well. A search returning three
#: cached foods is probably missing better matches; one returning twenty is not.
#:
#: Applies to `search_foods` — the *resolver*, used by photo scanning. The
#: browse search below deliberately does not top up from USDA.
LOCAL_RESULT_THRESHOLD = 8

#: How the browse search ranks a food, before its name is even scored.
#:
#: Lower is better, and the order is the app's answer to "what is this for". A
#: hand-curated food with a photograph and a French name beats a Tunisian table
#: entry, which beats your own foods, which beat the French table, which beats a
#: raw USDA row that nobody here has ever looked at.
#:
#: This exists because USDA writes names for a database rather than for a person
#: — a grilled chicken breast is filed as "Chicken, broilers or fryers, breast,
#: meat only, cooked, roasted" — and twenty-five of those is the wall of text
#: this app is trying not to be.

#: Tiers a browsing user sees without qualification. Anything above this — USDA
#: and Open Food Facts — is a fallback, not a result.
CURATED_TIERS = 3
REFERENCE_TIER = 4

SEARCH_TIER = case(
    (Food.kind == FoodKind.CATALOGUE, 0),
    (Food.source == FoodSource.INNTA, 1),
    (Food.owner_id.is_not(None), 2),
    (Food.source == FoodSource.CIQUAL, 3),
    else_=REFERENCE_TIER,
)

#: How many raw database rows to offer when nothing curated matches.
#:
#: Two, not twenty. The point is to answer "we have something, but it is not one
#: of ours" without turning the screen back into the list this change removed.
FALLBACK_LIMIT = 2

#: USDA name segments that carry no meaning for somebody logging lunch.
#:
#: USDA names are `HeadNoun, qualifier, qualifier, …` and the qualifiers are
#: written for a food scientist. Dropping the ones that describe *sampling*
#: rather than *food* turns "Chicken, broilers or fryers, breast, meat only,
#: cooked, roasted" into "Chicken, breast, cooked, roasted".
#:
#: Only the name is touched. No number, no source, no id — provenance is
#: unchanged and the original is still one lookup away by `source_id`.
NAME_NOISE = frozenset(
    {
        "broilers or fryers",
        "all classes",
        "meat only",
        "meat and skin",
        "composite of trimmed retail cuts",
        "separable lean only",
        "separable lean and fat",
        "trimmed to 1/8 fat",
        "trimmed to 0 fat",
        "raw or unprepared",
        "unprepared",
        "includes usda commodity food a099",
        "commercially prepared",
        "nfs",
    }
)

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


async def search_local(
    session: AsyncSession,
    query: str,
    limit: int,
    owner_id: uuid.UUID | None,
    *,
    max_tier: int | None = None,
    min_tier: int | None = None,
) -> list[Food]:
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

    # noqa comments, not a rewrite: ruff reads an upper-case name on the left as
    # a constant and suggests flipping these. `SEARCH_TIER` is a SQL expression,
    # and `max_tier >= SEARCH_TIER` reads backwards for something whose whole
    # meaning is "this tier or better".
    tier_filters = []
    if max_tier is not None:
        tier_filters.append(SEARCH_TIER <= max_tier)  # noqa: SIM300
    if min_tier is not None:
        tier_filters.append(SEARCH_TIER >= min_tier)  # noqa: SIM300

    result = await session.execute(
        select(Food)
        # Tier before text score. A curated Tunisian food that matches one word
        # should outrank a USDA row that matches three, because the user is
        # picking from this list by eye.
        .where(*tier_filters)
        # AI estimates are never returned by a search. They exist only so a
        # scanned food the databases could not identify still has a row to log
        # against, and they must not leak into a normal food search where the
        # user would have no idea the numbers were not measured.
        .where(Food.source != FoodSource.AI_ESTIMATE)
        # Three ways a food may be visible:
        #   - it has no owner (USDA, Open Food Facts, the catalogue)
        #   - you wrote it
        #   - a human approved it into the shared database
        #
        # Without the owner clause every custom food was searchable by
        # everybody, which is both a privacy leak and an open door. Approval is
        # the *only* route by which one user's typing reaches another's search,
        # and it runs through a person — see api/v1/review.py.
        .where(
            or_(
                Food.owner_id.is_(None),
                Food.owner_id == owner_id,
                Food.review_status == ReviewStatus.APPROVED,
            )
        )
        # Withdrawn foods are gone from search but not from the database — see
        # `Food.withdrawn_at`. A food somebody reported and an admin upheld must
        # stop being *offered*, while every diary entry already pointing at it
        # keeps rendering. Excluded here rather than deleted, because deleting
        # would take that history with it.
        .where(Food.withdrawn_at.is_(None))
        .where(score > 0)
        .order_by(SEARCH_TIER, score.desc(), func.length(Food.name), Food.name)
        .limit(limit)
    )
    return list(result.scalars())


def readable_name(name: str) -> str:
    """A USDA name with its laboratory qualifiers removed.

    `Chicken, broilers or fryers, breast, meat only, cooked, roasted` becomes
    `Chicken, breast, cooked, roasted`. Segments describing how a sample was
    prepared or graded go; segments describing the food stay.

    **Renaming, not renumbering.** No nutrition value is touched, `source` and
    `source_id` are unchanged, and the original name is one lookup away. The
    rule this project runs on is about inventing *numbers*; a name written for a
    food scientist is not a fact worth preserving on a phone screen.

    Conservative on purpose: if stripping leaves nothing, the original is
    returned. A confusing name beats an empty one.
    """
    segments = [part.strip() for part in name.split(",")]
    kept = [s for s in segments if s and s.lower() not in NAME_NOISE]
    if not kept:
        return name
    return ", ".join(kept[:4])


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
            # Never overwrite a curated catalogue row or an approved/corrected food.
            #
            # A catalogue food, a corrected food, or an approved custom food must
            # maintain its hand-verified or admin-corrected figures, rather than
            # being silently overwritten by an unrevised upstream fetch.
            where=(Food.kind != FoodKind.CATALOGUE) & (Food.review_status != ReviewStatus.APPROVED),
        )
        .returning(Food.id)
    )
    food_id = (await session.execute(statement)).scalar_one_or_none()

    if food_id is None:
        # The `where` above filtered the update out, so ON CONFLICT did nothing
        # and RETURNING gave back no row. That is not an error — it is the
        # catalogue row being protected — but the caller still needs its id.
        food_id = (
            await session.execute(
                select(Food.id).where(
                    Food.source == normalised["source"],
                    Food.source_id == normalised["source_id"],
                )
            )
        ).scalar_one()

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
    session: AsyncSession,
    query: str,
    *,
    limit: int,
    owner_id: uuid.UUID | None = None,
    client: UsdaClient | None = None,
) -> tuple[list[Food], bool]:
    """Search the cache, topping up from USDA when thin.

    Returns the foods and whether upstream was unavailable, so the app can tell
    the user "these are cached results" instead of silently showing a short list
    as though it were complete.
    """
    local = await search_local(session, query, limit, owner_id)
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


async def browse_search(
    session: AsyncSession,
    query: str,
    *,
    limit: int,
    owner_id: uuid.UUID | None = None,
    client: UsdaClient | None = None,
) -> tuple[list[Food], bool]:
    """Search as a *person* reads it: curated first, USDA only as a last resort.

    Separate from `search_foods` because the two have different jobs and only
    look alike. This one produces a short list somebody chooses from by eye.
    That one resolves a name the photo scanner produced, where the user never
    sees the candidates — only the numbers attached to the winner. Merging them
    would mean either hiding USDA from the scanner, which breaks it, or showing
    USDA to the user, which is the thing being fixed.

    **USDA never appears alongside curated results.** Not ranked below them —
    absent. A list that is half curated Tunisian food and half laboratory names
    is still the confusing list, just sorted. Only when nothing curated matches
    at all does a capped fallback appear, so the answer to a search for
    "quinoa" is two rows rather than nothing.

    Returns the foods and whether upstream was unreachable, so the app can say
    "these are cached results" instead of presenting a short list as complete.
    """
    curated = await search_local(session, query, limit, owner_id, max_tier=CURATED_TIERS)
    if curated:
        return curated, False

    cached_reference = await search_local(
        session, query, FALLBACK_LIMIT, owner_id, min_tier=REFERENCE_TIER
    )
    if cached_reference:
        return cached_reference, False

    # Nothing at all locally. Ask USDA once, keep at most two, and store what
    # comes back — the cache is what stops the next person paying for the same
    # question.
    usda = client or UsdaClient()
    try:
        payloads = await usda.search(query, page_size=FALLBACK_LIMIT)
    except UsdaUnavailable:
        logger.warning("USDA unavailable; nothing to offer for %r", query)
        return [], True

    fetched: list[Food] = []
    for payload in payloads[:FALLBACK_LIMIT]:
        try:
            fetched.append(await upsert_food(session, normalise_food(payload)))
        except UnusableFood as exc:
            logger.debug("Skipping unusable USDA food: %s", exc)

    await session.commit()
    return fetched, False
