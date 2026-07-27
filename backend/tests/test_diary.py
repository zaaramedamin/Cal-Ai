"""Diary logging, totals and the nutrient snapshot."""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.food import Food


def profile_today() -> date:
    """Today *in the timezone the test profiles declare*, which is UTC.

    Not `date.today()`. That returns the machine's local date, and the server
    decides which day an entry belongs to from the profile's timezone — so on a
    machine running ahead of UTC, a test computing "yesterday" locally is
    handing the server today's date and asserting it lands on a different day.

    The suite passed for months and began failing at 00:22 local / 23:22 UTC,
    which is exactly the one-hour window where the two disagree. A test for
    timezone-sensitive behaviour has to speak the same timezone as the code it
    is testing.
    """
    return datetime.now(UTC).date()


PROFILE = {
    "sex": "male",
    "birth_date": "1996-05-20",
    "height_cm": 180,
    "weight_kg": 80,
    "activity_level": "moderate",
    "goal": "maintain",
    "timezone": "UTC",
}


def onboarded(client: TestClient, email: str = "diary@example.com") -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.put("/api/v1/profile", json=PROFILE, headers=headers)
    return headers


async def make_food(session: AsyncSession, **overrides) -> Food:
    """A cached food with fibre deliberately absent, mirroring real USDA data."""
    food = Food(
        source="usda",
        source_id=overrides.pop("source_id", "test-1"),
        name=overrides.pop("name", "Chicken breast, raw"),
        kcal=overrides.pop("kcal", 165),
        protein_g=overrides.pop("protein_g", 31),
        carbs_g=overrides.pop("carbs_g", 0),
        fat_g=overrides.pop("fat_g", 3.6),
        # Absent by default, mirroring real USDA Foundation data.
        fibre_g=overrides.pop("fibre_g", None),
        **overrides,
    )
    session.add(food)
    await session.commit()
    await session.refresh(food)
    return food


async def test_logging_snapshots_nutrients_for_the_quantity(
    client: TestClient, session: AsyncSession
) -> None:
    """200 g of a 165 kcal/100 g food is 330 kcal, stored on the entry."""
    food = await make_food(session)
    headers = onboarded(client)

    response = client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "lunch", "quantity_grams": 200},
        headers=headers,
    )

    assert response.status_code == 201
    entry = response.json()
    assert entry["kcal"] == 330.0
    assert entry["protein_g"] == 62.0
    assert entry["food_name"] == "Chicken breast, raw"


async def test_snapshot_survives_the_food_changing(
    client: TestClient, session: AsyncSession
) -> None:
    """The central claim of the design.

    USDA revises values. Last Tuesday's lunch must not silently change when it
    does — the diary records what you ate, not a live query against current
    reference data.
    """
    food = await make_food(session)
    headers = onboarded(client)

    client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "lunch", "quantity_grams": 100},
        headers=headers,
    )

    food.kcal = 999
    await session.commit()

    day = client.get("/api/v1/diary", headers=headers).json()
    assert day["totals"]["kcal"] == 165.0, "a revised food must not rewrite history"


async def test_snapshot_survives_the_food_being_deleted(
    client: TestClient, session: AsyncSession
) -> None:
    """Deleting a food must not punch a hole in someone's history."""
    food = await make_food(session)
    headers = onboarded(client)

    client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "dinner", "quantity_grams": 150},
        headers=headers,
    )

    await session.delete(food)
    await session.commit()

    day = client.get("/api/v1/diary", headers=headers).json()
    entries = [entry for meal in day["meals"] for entry in meal["entries"]]
    assert len(entries) == 1
    assert entries[0]["food_name"] == "Chicken breast, raw"
    assert entries[0]["food_id"] is None
    assert day["totals"]["kcal"] == 247.5


async def test_missing_nutrients_stay_missing_through_logging(
    client: TestClient, session: AsyncSession
) -> None:
    """None must not become 0 by passing through a multiplication."""
    food = await make_food(session)
    headers = onboarded(client)

    entry = client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "lunch", "quantity_grams": 100},
        headers=headers,
    ).json()

    assert entry["fibre_g"] is None


async def test_day_totals_flag_partial_nutrients(
    client: TestClient, session: AsyncSession
) -> None:
    """A total summed over holes is not a total.

    One food reports fibre, one does not. The sum is 3 g, but presenting that as
    the day's fibre would be too low and look authoritative — so it is flagged.
    """
    with_fibre = await make_food(session, source_id="f1", name="Oats", fibre_g=10)
    without = await make_food(session, source_id="f2", name="Chicken")
    headers = onboarded(client)

    for food in (with_fibre, without):
        client.post(
            "/api/v1/diary",
            json={"food_id": str(food.id), "meal_slot": "breakfast", "quantity_grams": 30},
            headers=headers,
        )

    totals = client.get("/api/v1/diary", headers=headers).json()["totals"]
    assert totals["fibre_g"] == 3.0
    assert "fibre_g" in totals["partial"]


async def test_totals_are_not_partial_when_every_entry_reports(
    client: TestClient, session: AsyncSession
) -> None:
    food = await make_food(session, fibre_g=10)
    headers = onboarded(client)

    client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "lunch", "quantity_grams": 100},
        headers=headers,
    )

    totals = client.get("/api/v1/diary", headers=headers).json()["totals"]
    assert totals["fibre_g"] == 10.0
    # Only fibre is asserted complete. The other optional nutrients are still
    # absent on this food, so they remain flagged — which is the correct answer,
    # not an oversight.
    assert "fibre_g" not in totals["partial"]


async def test_day_groups_by_meal_and_compares_to_target(
    client: TestClient, session: AsyncSession
) -> None:
    food = await make_food(session)
    headers = onboarded(client)

    client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "lunch", "quantity_grams": 100},
        headers=headers,
    )

    day = client.get("/api/v1/diary", headers=headers).json()
    slots = {meal["meal_slot"]: len(meal["entries"]) for meal in day["meals"]}

    assert slots == {"breakfast": 0, "lunch": 1, "dinner": 0, "snack": 0}
    assert day["target_calories"] == 2759
    assert day["remaining_calories"] == 2759 - 165


async def test_remaining_calories_can_go_negative(
    client: TestClient, session: AsyncSession
) -> None:
    """Going over is information. Clamping it to zero would hide it."""
    food = await make_food(session)
    headers = onboarded(client)

    client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "dinner", "quantity_grams": 3000},
        headers=headers,
    )

    day = client.get("/api/v1/diary", headers=headers).json()
    assert day["remaining_calories"] < 0


async def test_editing_quantity_rescales_the_snapshot(
    client: TestClient, session: AsyncSession
) -> None:
    food = await make_food(session)
    headers = onboarded(client)

    entry = client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "lunch", "quantity_grams": 100},
        headers=headers,
    ).json()

    updated = client.patch(
        f"/api/v1/diary/{entry['id']}", json={"quantity_grams": 200}, headers=headers
    ).json()

    assert updated["quantity_grams"] == 200
    assert float(updated["kcal"]) == 330.0


async def test_deleting_an_entry_removes_it_from_totals(
    client: TestClient, session: AsyncSession
) -> None:
    food = await make_food(session)
    headers = onboarded(client)

    entry = client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "lunch", "quantity_grams": 100},
        headers=headers,
    ).json()

    assert client.delete(f"/api/v1/diary/{entry['id']}", headers=headers).status_code == 204
    assert client.get("/api/v1/diary", headers=headers).json()["totals"]["kcal"] == 0


async def test_entries_are_isolated_between_users(
    client: TestClient, session: AsyncSession
) -> None:
    """404 rather than 403 for someone else's entry: a 403 would confirm the id
    exists and let an attacker enumerate them."""
    food = await make_food(session)
    alice = onboarded(client, "alice-diary@example.com")
    bob = onboarded(client, "bob-diary@example.com")

    entry = client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "lunch", "quantity_grams": 100},
        headers=alice,
    ).json()

    assert client.patch(
        f"/api/v1/diary/{entry['id']}", json={"quantity_grams": 50}, headers=bob
    ).status_code == 404
    assert client.delete(f"/api/v1/diary/{entry['id']}", headers=bob).status_code == 404
    assert client.get("/api/v1/diary", headers=bob).json()["totals"]["kcal"] == 0


async def test_past_days_can_be_read_and_are_separate(
    client: TestClient, session: AsyncSession
) -> None:
    food = await make_food(session)
    headers = onboarded(client)
    yesterday = (profile_today() - timedelta(days=1)).isoformat()

    client.post(
        "/api/v1/diary",
        json={
            "food_id": str(food.id),
            "meal_slot": "lunch",
            "quantity_grams": 100,
            "local_date": yesterday,
        },
        headers=headers,
    )

    assert client.get("/api/v1/diary", headers=headers).json()["totals"]["kcal"] == 0
    assert (
        client.get(f"/api/v1/diary?day={yesterday}", headers=headers).json()["totals"]["kcal"]
        == 165.0
    )


async def test_future_dates_are_rejected(client: TestClient, session: AsyncSession) -> None:
    food = await make_food(session)
    headers = onboarded(client)
    tomorrow = (profile_today() + timedelta(days=1)).isoformat()

    response = client.post(
        "/api/v1/diary",
        json={
            "food_id": str(food.id),
            "meal_slot": "lunch",
            "quantity_grams": 100,
            "local_date": tomorrow,
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_logging_requires_onboarding(client: TestClient, session: AsyncSession) -> None:
    food = await make_food(session)
    token = client.post(
        "/api/v1/auth/register",
        json={"email": "no-profile@example.com", "password": "correct-horse-battery"},
    ).json()["access_token"]

    response = client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "lunch", "quantity_grams": 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_diary_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/diary").status_code == 401
    assert client.post("/api/v1/diary", json={}).status_code == 401


# --------------------------------------------------------------------------- #
# Quick add: the user's own staples, ready to re-log in one tap.
# --------------------------------------------------------------------------- #


async def test_quick_add_is_empty_before_anything_is_logged(client: TestClient) -> None:
    """A new user gets no chips rather than a placeholder row."""
    headers = onboarded(client, "quick-empty@example.com")

    response = client.get("/api/v1/foods/quick-add", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_quick_add_ranks_by_frequency_not_recency(
    client: TestClient, session: AsyncSession
) -> None:
    """"Your usuals", not "your history".

    The most recently eaten food is often the unusual one — the restaurant meal,
    the one-off. What earns a place on the dashboard is the thing eaten
    repeatedly, so a food logged three times outranks one logged later but once.
    """
    staple = await make_food(session, name="Oats, rolled", source_id="oats")
    oneoff = await make_food(session, name="Cheesecake", source_id="cake")
    headers = onboarded(client, "quick-rank@example.com")

    for _ in range(3):
        client.post(
            "/api/v1/diary",
            json={"food_id": str(staple.id), "meal_slot": "breakfast", "quantity_grams": 60},
            headers=headers,
        )
    # Logged last, so recency alone would put it first.
    client.post(
        "/api/v1/diary",
        json={"food_id": str(oneoff.id), "meal_slot": "snack", "quantity_grams": 120},
        headers=headers,
    )

    results = client.get("/api/v1/foods/quick-add", headers=headers).json()

    assert [row["name"] for row in results] == ["Oats, rolled", "Cheesecake"]
    assert results[0]["times_logged"] == 3


async def test_quick_add_remembers_the_last_quantity_and_slot(
    client: TestClient, session: AsyncSession
) -> None:
    """The field that makes the chip worth having.

    Without the remembered amount, tapping a chip still has to ask "how much?"
    and has saved the user nothing.
    """
    food = await make_food(session, name="Oats, rolled", source_id="oats")
    headers = onboarded(client, "quick-qty@example.com")

    client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "breakfast", "quantity_grams": 60},
        headers=headers,
    )
    # A later, different amount must win — the chip should offer what you did
    # last time, not what you did first.
    client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "dinner", "quantity_grams": 85},
        headers=headers,
    )

    row = client.get("/api/v1/foods/quick-add", headers=headers).json()[0]

    assert row["last_quantity_grams"] == 85
    assert row["last_meal_slot"] == "dinner"
    assert row["times_logged"] == 2


async def test_quick_add_is_per_user(client: TestClient, session: AsyncSession) -> None:
    """One person's staples must never appear on another person's dashboard."""
    food = await make_food(session, name="Oats, rolled", source_id="oats")
    mine = onboarded(client, "quick-mine@example.com")
    theirs = onboarded(client, "quick-theirs@example.com")

    client.post(
        "/api/v1/diary",
        json={"food_id": str(food.id), "meal_slot": "breakfast", "quantity_grams": 60},
        headers=mine,
    )

    assert client.get("/api/v1/foods/quick-add", headers=mine).json() != []
    assert client.get("/api/v1/foods/quick-add", headers=theirs).json() == []


async def test_quick_add_route_is_not_swallowed_by_the_food_detail_route(
    client: TestClient,
) -> None:
    """Regression: FastAPI matches routes in definition order.

    Declared after `/{food_id}`, this path would be parsed as a UUID and answer
    422 forever. The bug is invisible until someone reorders the file.
    """
    response = client.get("/api/v1/foods/quick-add", headers=onboarded(client, "quick-route@e.com"))

    assert response.status_code == 200
