"""Search as a person reads it, rather than as a machine resolves it.

The app is for Tunisia first. USDA writes names for a database — a grilled
chicken breast is filed as *Chicken, broilers or fryers, breast, meat only,
cooked, roasted* — and twenty-five of those was the wall of text this change
removes.

The property under test is narrow and easy to lose: **USDA never appears
alongside curated results.** Not ranked below them, absent. A list that is half
Tunisian food and half laboratory names is still the confusing list, merely
sorted. Only when nothing curated matches at all does a capped fallback appear.

The other half is that `search_foods` — the resolver photo scanning uses — is
*unchanged*. Its candidates are never shown to anybody; only the winner's
numbers reach the screen. Hiding USDA from it would break scanning outright,
which is why the two are separate functions rather than one with a flag.
"""

import uuid

import pytest

from app.db.models.food import Food, FoodKind, FoodSource
from app.services.food_cache import (
    CURATED_TIERS,
    FALLBACK_LIMIT,
    browse_search,
    readable_name,
    search_local,
)


async def add(session, *, source, name, kind=FoodKind.REFERENCE, owner_id=None, **extra):
    food = Food(
        source=source,
        source_id=f"{source}-{uuid.uuid4().hex[:10]}",
        name=name,
        kind=kind,
        owner_id=owner_id,
        kcal=100,
        protein_g=5,
        carbs_g=10,
        fat_g=2,
        **extra,
    )
    session.add(food)
    await session.commit()
    return food


class NoUsda:
    """A USDA client that must never be called.

    Asserting on absence directly: a test that merely checked the results were
    curated would still pass if the code had spent a request from the shared
    hourly budget on the way there.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query, page_size=10):  # noqa: ANN001, ARG002
        self.calls += 1
        return []


# --------------------------------------------------------------------------- #
# Curated first, USDA absent
# --------------------------------------------------------------------------- #


async def test_curated_results_hide_usda_entirely(session) -> None:
    """The whole point. Not "ranked lower" — not returned."""
    await add(session, source=FoodSource.INNTA, name="Pain, tabouna")
    await add(session, source=FoodSource.USDA, name="Bread, tabouna style, commercial")

    usda = NoUsda()
    found, _ = await browse_search(session, "tabouna", limit=6, client=usda)

    assert [f.source for f in found] == [FoodSource.INNTA]
    assert usda.calls == 0, "a curated hit must not also cost a USDA request"


async def test_the_tunisian_table_outranks_the_french_one(session) -> None:
    """Both are curated, so both are shown — but this app is for Tunisia."""
    await add(session, source=FoodSource.CIQUAL, name="Couscous, cuit")
    await add(session, source=FoodSource.INNTA, name="Couscous sec")

    found, _ = await browse_search(session, "couscous", limit=6, client=NoUsda())

    assert [f.source for f in found] == [FoodSource.INNTA, FoodSource.CIQUAL]


async def test_the_catalogue_outranks_everything(session) -> None:
    """A hand-curated food has a photograph and a name in both languages.

    Nothing else in the database does, so it is the best thing to show first.
    """
    await add(session, source=FoodSource.INNTA, name="Banane, pulpe fraîche")
    await add(
        session,
        source=FoodSource.USDA,
        name="Banana curated",
        kind=FoodKind.CATALOGUE,
        slug=f"banana-{uuid.uuid4().hex[:6]}",
        category="Fruit",
    )

    found, _ = await browse_search(session, "banan", limit=6, client=NoUsda())

    assert found[0].kind == FoodKind.CATALOGUE


async def test_your_own_food_is_curated_enough_to_show(session) -> None:
    """You typed it off a label. That beats a row nobody here has read."""
    from app.db.models.user import User

    owner = uuid.uuid4()
    # A real user row, because `owner_id` is a foreign key.
    user = User(id=owner, email=f"{owner.hex[:8]}@example.com", password_hash="x")
    session.add(user)
    await session.commit()

    await add(session, source=FoodSource.USER, name="Zzqx my bar", owner_id=owner)

    found, _ = await browse_search(session, "zzqx", limit=6, owner_id=owner, client=NoUsda())

    assert [f.name for f in found] == ["Zzqx my bar"]


# --------------------------------------------------------------------------- #
# The fallback
# --------------------------------------------------------------------------- #


async def test_cached_usda_answers_when_nothing_curated_matches(session) -> None:
    """Two rows rather than nothing.

    Returning an empty screen the first time somebody types "quinoa" would be
    simple and useless.
    """
    for n in range(5):
        await add(session, source=FoodSource.USDA, name=f"Quinoa, variety {n}")

    usda = NoUsda()
    found, _ = await browse_search(session, "quinoa", limit=6, client=usda)

    assert len(found) == FALLBACK_LIMIT, "capped, not the whole list"
    assert usda.calls == 0, "the cache already had an answer"


async def test_the_fallback_is_capped_even_when_upstream_offers_more(session) -> None:
    class Generous:
        async def search(self, query, page_size=10):  # noqa: ANN001, ARG002
            return [
                {
                    "fdcId": 900000 + n,
                    "description": f"Quinoa, kind {n}",
                    "foodNutrients": [
                        {"nutrientNumber": "208", "value": 120},
                        {"nutrientNumber": "203", "value": 4},
                        {"nutrientNumber": "205", "value": 21},
                        {"nutrientNumber": "204", "value": 2},
                    ],
                }
                for n in range(10)
            ]

    found, _ = await browse_search(session, "quinoa", limit=6, client=Generous())

    assert len(found) <= FALLBACK_LIMIT


async def test_an_unreachable_usda_is_reported_not_hidden(session) -> None:
    """The app says "we could not look" rather than "there is nothing"."""
    from app.services.usda import UsdaUnavailable

    class Down:
        async def search(self, query, page_size=10):  # noqa: ANN001, ARG002
            raise UsdaUnavailable("down")

    found, unavailable = await browse_search(session, "quinoa", limit=6, client=Down())

    assert found == []
    assert unavailable is True


# --------------------------------------------------------------------------- #
# Tier filtering
# --------------------------------------------------------------------------- #


async def test_max_tier_excludes_reference_rows(session) -> None:
    await add(session, source=FoodSource.USDA, name="Zzqxfood, raw")

    assert await search_local(session, "zzqxfood", 10, None) != []
    assert await search_local(session, "zzqxfood", 10, None, max_tier=CURATED_TIERS) == []


async def test_withdrawn_foods_never_reach_the_fallback(session) -> None:
    """Withdrawal has to hold on every route into search, not just the main one."""
    from datetime import UTC, datetime

    food = await add(session, source=FoodSource.USDA, name="Zzqxwithdrawn, raw")
    food.withdrawn_at = datetime.now(UTC)
    await session.commit()

    found, _ = await browse_search(session, "zzqxwithdrawn", limit=6, client=NoUsda())

    assert found == []


# --------------------------------------------------------------------------- #
# Readable names
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Chicken, broilers or fryers, breast, meat only, cooked, roasted",
            "Chicken, breast, cooked, roasted",
        ),
        # "raw" stays. It describes the food, not how it was sampled, and
        # dropping it would make raw and cooked beef read identically.
        (
            "Beef, ground, 85% lean meat / 15% fat, raw",
            "Beef, ground, 85% lean meat / 15% fat, raw",
        ),
        (
            "Pork, fresh, loin, separable lean only, cooked, broiled",
            "Pork, fresh, loin, cooked",
        ),
        # Already readable, and must survive untouched.
        ("Bananas, raw", "Bananas, raw"),
        ("Quinoa, cooked", "Quinoa, cooked"),
    ],
)
def test_laboratory_qualifiers_are_dropped(raw: str, expected: str) -> None:
    assert readable_name(raw) == expected


def test_a_name_that_is_all_noise_survives() -> None:
    """A confusing name beats an empty one.

    Stripping is a display nicety; losing the food's identity is not.
    """
    assert readable_name("meat only") == "meat only"


def test_renaming_never_touches_provenance() -> None:
    """`readable_name` is a string function and nothing else.

    Written as a test because the temptation to "tidy up the database while we
    are here" is exactly how a row ends up claiming a source its name no longer
    matches.
    """
    original = "Chicken, broilers or fryers, breast, meat only, cooked, roasted"

    assert readable_name(original) != original
    assert original == "Chicken, broilers or fryers, breast, meat only, cooked, roasted"


# --------------------------------------------------------------------------- #
# The resolver is untouched
# --------------------------------------------------------------------------- #


async def test_the_scan_resolver_still_sees_usda(session) -> None:
    """Photo scanning resolves a name the model produced against USDA.

    Its candidates are never shown to anybody — only the winner's numbers reach
    the screen — so hiding USDA from it would break scanning while fixing
    nothing. This is why `browse_search` and `search_foods` are two functions.
    """
    from app.services.food_cache import search_foods

    await add(session, source=FoodSource.USDA, name="Zzqxresolve, raw")

    found, _ = await search_foods(session, "zzqxresolve", limit=5, client=NoUsda())

    assert [f.name for f in found] == ["Zzqxresolve, raw"]


async def test_the_endpoint_returns_a_short_list(client, session) -> None:
    """The default was 25. A list that long is a thing to read, not to choose
    from."""
    from tests.test_reports import account

    for n in range(20):
        await add(session, source=FoodSource.INNTA, name=f"Zzqxmany numero {n}")

    headers = account(client, "searcher@example.com")
    body = client.get(
        "/api/v1/foods/search", headers=headers, params={"q": "zzqxmany"}
    ).json()

    assert len(body["results"]) == 6


async def test_the_endpoint_cleans_usda_names(client, session) -> None:
    from tests.test_reports import account

    await add(
        session,
        source=FoodSource.USDA,
        name="Zzqxclean, broilers or fryers, breast, meat only, cooked",
    )

    headers = account(client, "searcher@example.com")
    body = client.get(
        "/api/v1/foods/search", headers=headers, params={"q": "zzqxclean"}
    ).json()

    assert body["results"][0]["name"] == "Zzqxclean, breast, cooked"


async def test_the_endpoint_leaves_curated_names_alone(client, session) -> None:
    """Those names were written by a person for this purpose already."""
    from tests.test_reports import account

    await add(session, source=FoodSource.INNTA, name="Zzqxkeep, pulpe, fraîche, crue, entière")

    headers = account(client, "searcher@example.com")
    body = client.get(
        "/api/v1/foods/search", headers=headers, params={"q": "zzqxkeep"}
    ).json()

    assert body["results"][0]["name"] == "Zzqxkeep, pulpe, fraîche, crue, entière"
