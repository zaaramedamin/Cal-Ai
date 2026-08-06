"""Deleting an account.

The one irreversible action in the app. Two things it has to get right, and they
pull in opposite directions:

* **Everything personal goes.** Diary, weights, profile, meals, recipes,
  sessions, private foods. Mostly the foreign keys' job, which is the point —
  a deletion *script* is a list somebody has to remember to extend when a table
  is added, and the day they forget is the day personal data survives a
  deletion request.
* **Approved contributions stay.** A food this person offered and a reviewer
  approved is in other people's diaries. Cascading it away would silently
  rewrite what those people ate.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models.diary import DiaryEntry
from app.db.models.food import Food, FoodSource, ReviewStatus
from app.db.models.user import User

PASSWORD = "correct-horse-battery"
PROFILE = {
    "sex": "male",
    "birth_date": "1996-05-20",
    "height_cm": 180,
    "weight_kg": 80,
    "activity_level": "moderate",
    "goal": "maintain",
    "timezone": "UTC",
}


def register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_deleting_needs_the_right_email(client: TestClient) -> None:
    """A checkbox is something a thumb does by accident. Typing your own address
    is not."""
    headers = register(client, "leaver@example.com")

    response = client.request(
        "DELETE", "/api/v1/users/me", headers=headers, json={"email": "someone@else.com"}
    )

    assert response.status_code == 400
    assert "not the email address" in response.json()["detail"]


def test_the_check_ignores_case_and_spacing(client: TestClient) -> None:
    """Refusing "  Leaver@Example.com " would be pedantry, not safety."""
    headers = register(client, "leaver@example.com")

    response = client.request(
        "DELETE", "/api/v1/users/me", headers=headers, json={"email": "  Leaver@Example.com "}
    )

    assert response.status_code == 204


def test_deleting_requires_being_signed_in(client: TestClient) -> None:
    response = client.request("DELETE", "/api/v1/users/me", json={"email": "a@b.com"})
    assert response.status_code == 401


async def test_the_account_and_its_diary_are_gone(client: TestClient, session) -> None:
    headers = register(client, "leaver@example.com")
    client.put("/api/v1/profile", headers=headers, json=PROFILE)

    food = Food(
        source=FoodSource.USDA,
        source_id=f"usda-{uuid.uuid4().hex[:8]}",
        name="Zzqx test food",
        kcal=100,
        protein_g=1,
        carbs_g=1,
        fat_g=1,
    )
    session.add(food)
    await session.commit()

    logged = client.post(
        "/api/v1/diary",
        headers=headers,
        json={"food_id": str(food.id), "meal_slot": "lunch", "quantity_grams": 100},
    )
    assert logged.status_code == 201

    assert client.request(
        "DELETE", "/api/v1/users/me", headers=headers, json={"email": "leaver@example.com"}
    ).status_code == 204

    gone = (
        await session.execute(select(User).where(User.email == "leaver@example.com"))
    ).scalar_one_or_none()
    assert gone is None
    assert (await session.execute(select(DiaryEntry))).scalars().all() == []


async def test_the_token_stops_working_immediately(client: TestClient) -> None:
    """No grace period. The account is gone, so the session is too."""
    headers = register(client, "leaver@example.com")
    client.request(
        "DELETE", "/api/v1/users/me", headers=headers, json={"email": "leaver@example.com"}
    )

    assert client.get("/api/v1/users/me", headers=headers).status_code == 401


async def test_a_private_food_goes_with_its_author(client: TestClient, session) -> None:
    """Nobody else could ever see it, so nobody else can miss it."""
    headers = register(client, "leaver@example.com")
    created = client.post(
        "/api/v1/foods",
        headers=headers,
        json={"name": "Zzqx private", "kcal": 100, "protein_g": 1, "carbs_g": 1, "fat_g": 1},
    )
    assert created.status_code == 201

    client.request(
        "DELETE", "/api/v1/users/me", headers=headers, json={"email": "leaver@example.com"}
    )

    remaining = (
        await session.execute(select(Food).where(Food.name == "Zzqx private"))
    ).scalar_one_or_none()
    assert remaining is None


async def test_an_approved_food_survives_and_is_detached(client: TestClient, session) -> None:
    """The one thing that must *not* cascade.

    An approved food is in other people's diaries. Deleting it would rewrite
    what they ate; leaving it attached would keep a link to a deleted account.
    So it stays, with `owner_id` cleared — the same rule that keeps a report's
    evidence after its reporter leaves.
    """
    headers = register(client, "leaver@example.com")
    created = client.post(
        "/api/v1/foods",
        headers=headers,
        json={"name": "Zzqx shared", "kcal": 100, "protein_g": 1, "carbs_g": 1, "fat_g": 1},
    )
    food_id = uuid.UUID(created.json()["id"])
    food = (await session.execute(select(Food).where(Food.id == food_id))).scalar_one()
    food.review_status = ReviewStatus.APPROVED
    await session.commit()

    assert client.request(
        "DELETE", "/api/v1/users/me", headers=headers, json={"email": "leaver@example.com"}
    ).status_code == 204

    survivor = (
        await session.execute(select(Food).where(Food.id == food_id))
    ).scalar_one_or_none()
    assert survivor is not None, "an approved food is in other people's diaries"
    await session.refresh(survivor)
    assert survivor.owner_id is None, "nothing identifying may stay attached"


@pytest.mark.parametrize("status_value", [ReviewStatus.PENDING, ReviewStatus.REJECTED])
async def test_unapproved_submissions_go(client: TestClient, session, status_value: str) -> None:
    """Only *approved* rows are shared. A pending or rejected one was never
    visible to anybody else, so there is nothing to preserve."""
    headers = register(client, "leaver@example.com")
    created = client.post(
        "/api/v1/foods",
        headers=headers,
        json={"name": "Zzqx pending", "kcal": 100, "protein_g": 1, "carbs_g": 1, "fat_g": 1},
    )
    food_id = uuid.UUID(created.json()["id"])
    food = (await session.execute(select(Food).where(Food.id == food_id))).scalar_one()
    food.review_status = status_value
    await session.commit()

    client.request(
        "DELETE", "/api/v1/users/me", headers=headers, json={"email": "leaver@example.com"}
    )

    assert (
        await session.execute(select(Food).where(Food.id == food_id))
    ).scalar_one_or_none() is None
