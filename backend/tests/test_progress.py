"""Progress: streaks, averages, BMI."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.progress import bmi_of, streak_from
from app.db.models.food import Food

PROFILE = {
    "sex": "male",
    "birth_date": "1996-05-20",
    "height_cm": 180,
    "weight_kg": 80,
    "activity_level": "moderate",
    "goal": "maintain",
    "timezone": "UTC",
}

TODAY = date(2026, 7, 27)


# --------------------------------------------------------------------------- #
# Streak logic — pure
# --------------------------------------------------------------------------- #


def days(*offsets: int) -> set[date]:
    return {TODAY - timedelta(days=offset) for offset in offsets}


def test_streak_counts_consecutive_days_ending_today() -> None:
    streak, logged_today = streak_from(days(0, 1, 2), TODAY)
    assert streak == 3
    assert logged_today


def test_streak_survives_an_unlogged_today() -> None:
    """Nothing logged *yet* today must not read as a broken streak.

    Breaking a 30-day streak at breakfast because lunch is not logged would make
    the number feel punitive and arbitrary. It breaks only after a full missed
    day.
    """
    streak, logged_today = streak_from(days(1, 2, 3), TODAY)
    assert streak == 3
    assert not logged_today


def test_streak_breaks_after_a_full_missed_day() -> None:
    streak, _ = streak_from(days(2, 3, 4), TODAY)
    assert streak == 0


def test_gap_in_history_stops_the_count() -> None:
    streak, _ = streak_from(days(0, 1, 3, 4), TODAY)
    assert streak == 2


def test_no_history_means_no_streak() -> None:
    streak, logged_today = streak_from(set(), TODAY)
    assert streak == 0
    assert not logged_today


# --------------------------------------------------------------------------- #
# BMI — pure
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("weight", "height", "expected_bmi", "category"),
    [
        (50, 180, 15.4, "underweight"),
        (70, 180, 21.6, "healthy"),
        (85, 180, 26.2, "overweight"),
        (100, 180, 30.9, "obese"),
    ],
)
def test_bmi_categories(weight: float, height: float, expected_bmi: float, category: str) -> None:
    bmi, label = bmi_of(weight, height)
    assert bmi == expected_bmi
    assert label == category


def test_bmi_boundary_is_healthy_at_18_5() -> None:
    """18.5 exactly is healthy, not underweight — boundaries belong to the
    category above them in the WHO tables."""
    bmi, label = bmi_of(18.5 * 1.8 * 1.8, 180)
    assert label == "healthy"


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #


def onboarded(client: TestClient, email: str = "progress@example.com") -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.put("/api/v1/profile", json=PROFILE, headers=headers)
    return headers


async def make_food(session: AsyncSession) -> Food:
    food = Food(
        source="usda", source_id="p1", name="Chicken", kcal=165, protein_g=31, carbs_g=0, fat_g=3.6
    )
    session.add(food)
    await session.commit()
    await session.refresh(food)
    return food


def test_progress_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/progress").status_code == 401


def test_progress_requires_onboarding(client: TestClient) -> None:
    token = client.post(
        "/api/v1/auth/register",
        json={"email": "bare@example.com", "password": "correct-horse-battery"},
    ).json()["access_token"]
    response = client.get("/api/v1/progress", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


async def test_progress_reflects_logged_days(client: TestClient, session: AsyncSession) -> None:
    food = await make_food(session)
    headers = onboarded(client)

    client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "lunch", "quantity_grams": 200},
        headers=headers,
    )

    body = client.get("/api/v1/progress", headers=headers).json()
    assert body["streak_days"] == 1
    assert body["logged_today"] is True
    assert body["weekly_average_kcal"] == 330.0
    assert len(body["last_7_days"]) == 7
    assert body["last_7_days"][-1]["kcal"] == 330.0


async def test_average_ignores_empty_days(client: TestClient, session: AsyncSession) -> None:
    """2,000 kcal on each of two days is an average of 2,000, not 571.

    Averaging in the five empty days would look rigorous and be misleading.
    """
    food = await make_food(session)
    headers = onboarded(client)
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    for day in (None, yesterday):
        payload = {"food_id": str(food.id), "meal_slot": "dinner", "quantity_grams": 400}
        if day:
            payload["local_date"] = day
        client.post("/api/v1/diary", json=payload, headers=headers)

    body = client.get("/api/v1/progress", headers=headers).json()
    assert body["weekly_average_kcal"] == 660.0


def test_progress_includes_weight_and_bmi(client: TestClient) -> None:
    headers = onboarded(client)

    body = client.get("/api/v1/progress", headers=headers).json()
    # Onboarding logged 80 kg at 180 cm -> BMI 24.7, top of the healthy band.
    assert body["current_weight_kg"] == 80.0
    assert body["bmi"] == 24.7
    assert body["bmi_category"] == "healthy"
    assert len(body["weight_series"]) == 1


def test_fresh_account_has_a_zero_streak(client: TestClient) -> None:
    headers = onboarded(client)
    body = client.get("/api/v1/progress", headers=headers).json()
    assert body["streak_days"] == 0
    assert body["logged_today"] is False
