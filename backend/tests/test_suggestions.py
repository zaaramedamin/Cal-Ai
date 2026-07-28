"""Meal suggestions: arithmetic over measured values.

The unit tests here exercise the ranking directly, because that is where the
judgement lives. A suggestion engine is easy to make plausible and hard to make
*right* — the failure mode is not a crash, it is confidently recommending a
700 kcal item to someone with 300 kcal left, which no exception will catch.
"""

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.food import Food
from app.services.suggestions import (
    MAX_PORTION_G,
    MIN_REMAINING_KCAL,
    Gap,
    suggest,
)
from tests.test_diary import PROFILE, make_food


def food(name: str, kcal: float, protein: float, carbs: float, fat: float) -> Food:
    """An unsaved Food. The ranking never touches the database."""
    return Food(
        source="usda",
        source_id=name,
        name=name,
        kcal=kcal,
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fat,
    )


CHICKEN = food("Chicken breast", 165, 31, 0, 3.6)
RICE = food("White rice", 130, 2.7, 28, 0.3)
OLIVE_OIL = food("Olive oil", 884, 0, 0, 100)
LETTUCE = food("Lettuce", 15, 1.4, 2.9, 0.2)


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #


def test_suggests_the_food_that_closes_the_biggest_gap() -> None:
    """Someone short on protein should be pointed at protein.

    Without the dominant-macro weighting the ranking degenerates into "whatever
    fits the most calories", which recommends the same energy-dense foods to
    everyone regardless of what they actually need.
    """
    gap = Gap(kcal=600, protein_g=50, carbs_g=5, fat_g=5)

    ranked = suggest([RICE, CHICKEN, LETTUCE], gap)

    assert ranked[0].food.name == "Chicken breast"
    assert "protein" in ranked[0].reason


def test_suggests_carbs_when_carbs_are_what_is_missing() -> None:
    """The same pool, a different gap, a different answer."""
    gap = Gap(kcal=600, protein_g=2, carbs_g=90, fat_g=5)

    ranked = suggest([RICE, CHICKEN, LETTUCE], gap)

    assert ranked[0].food.name == "White rice"
    assert "carbs" in ranked[0].reason


def test_never_suggests_a_portion_that_blows_the_calorie_budget() -> None:
    """The failure that matters.

    A suggestion the user cannot afford is worse than no suggestion: they either
    follow it and go over, or they learn to ignore the panel.
    """
    gap = Gap(kcal=200, protein_g=40, carbs_g=10, fat_g=10)

    ranked = suggest([CHICKEN, RICE, OLIVE_OIL], gap)

    assert ranked, "expected something to fit within 200 kcal"
    for item in ranked:
        assert item.kcal <= gap.kcal


def test_portions_stay_within_what_a_person_would_eat() -> None:
    """Arithmetically correct is not the same as sensible.

    Closing a 60 g fat gap from olive oil is "60 g of olive oil" by the maths and
    absurd in a kitchen, so portions are clamped regardless of how well the
    numbers work out.
    """
    gap = Gap(kcal=3000, protein_g=10, carbs_g=10, fat_g=200)

    ranked = suggest([OLIVE_OIL], gap)

    assert all(item.grams <= MAX_PORTION_G for item in ranked)


def test_says_nothing_when_the_day_is_full() -> None:
    """Silence is the correct output, not a filler recommendation."""
    assert suggest([CHICKEN, RICE], Gap(kcal=40, protein_g=20, carbs_g=20, fat_g=5)) == []
    assert suggest([CHICKEN, RICE], Gap(kcal=-300, protein_g=0, carbs_g=0, fat_g=0)) == []


def test_does_not_offer_the_same_food_twice() -> None:
    """The cache legitimately holds near-identical USDA rows for one food.

    Three variants of chicken breast in a four-item list looks broken, however
    correct each one is.
    """
    duplicate = food("chicken breast", 165, 31, 0, 3.6)

    ranked = suggest([CHICKEN, duplicate, RICE], Gap(kcal=800, protein_g=60, carbs_g=50, fat_g=20))

    names = [item.food.name.lower() for item in ranked]
    assert len(names) == len(set(names))


def test_dominant_macro_is_measured_in_calories_not_grams() -> None:
    """20 g of fat is a bigger gap than 20 g of protein — 180 kcal against 80.

    Ranking by grams would systematically over-recommend fat, because fat gaps
    are numerically smaller for the same amount of missing energy.
    """
    # Equal grams, so a gram-based comparison would call this a tie or pick
    # protein; by calories, fat is the larger shortfall.
    assert Gap(kcal=500, protein_g=20, carbs_g=0, fat_g=20).dominant_macro == "fat"
    # 120 kcal of protein against 90 of fat — protein now wins despite the
    # gram figures being closer together.
    assert Gap(kcal=500, protein_g=30, carbs_g=0, fat_g=10).dominant_macro == "protein"


def test_no_shortfall_means_no_dominant_macro() -> None:
    """All macros met but calories left: suggest on fit alone, not on a gap."""
    assert Gap(kcal=400, protein_g=-5, carbs_g=-10, fat_g=-2).dominant_macro is None


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #


def onboarded(client: TestClient, email: str) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.put("/api/v1/profile", json=PROFILE, headers=headers)
    return headers


async def test_endpoint_reports_the_remaining_budget(
    client: TestClient, session: AsyncSession
) -> None:
    """The numbers behind the suggestions are returned too.

    The panel says "you're 48 g short", so the app needs the same figures the
    ranking used — recomputing them client-side would be a second definition.
    """
    headers = onboarded(client, "sugg-budget@example.com")

    response = client.get("/api/v1/suggestions", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["remaining_kcal"] > 0
    assert body["remaining_protein_g"] > 0


async def test_endpoint_suggests_from_the_users_own_foods(
    client: TestClient, session: AsyncSession
) -> None:
    """A food the user actually eats beats a technically-optimal stranger."""
    chicken = await make_food(session, name="Chicken breast, grilled", source_id="ck")
    headers = onboarded(client, "sugg-own@example.com")
    client.post(
        "/api/v1/diary",
        json={"food_id": str(chicken.id), "meal_slot": "lunch", "quantity_grams": 100},
        headers=headers,
    )

    body = client.get("/api/v1/suggestions", headers=headers).json()

    assert any(s["food"]["name"] == "Chicken breast, grilled" for s in body["suggestions"])
    assert all(s["grams"] > 0 and s["kcal"] > 0 for s in body["suggestions"])
    assert all(s["reason"] for s in body["suggestions"])


async def test_endpoint_explains_itself_when_the_day_is_full(
    client: TestClient, session: AsyncSession
) -> None:
    """An empty panel with no explanation reads as a bug."""
    huge = await make_food(session, name="Enormous pie", source_id="pie", kcal=800)
    headers = onboarded(client, "sugg-full@example.com")
    for _ in range(4):
        client.post(
            "/api/v1/diary",
            json={"food_id": str(huge.id), "meal_slot": "dinner", "quantity_grams": 200},
            headers=headers,
        )

    body = client.get("/api/v1/suggestions", headers=headers).json()

    assert body["suggestions"] == []
    assert body["note"]
    assert body["remaining_kcal"] < MIN_REMAINING_KCAL


async def test_endpoint_requires_onboarding(client: TestClient) -> None:
    token = client.post(
        "/api/v1/auth/register",
        json={"email": "sugg-new@example.com", "password": "correct-horse-battery"},
    ).json()["access_token"]

    response = client.get("/api/v1/suggestions", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
