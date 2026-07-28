"""Composing meals from catalogue ingredients and logging them whole."""

import pytest
from fastapi.testclient import TestClient

PROFILE = {
    "sex": "male",
    "birth_date": "1996-05-20",
    "height_cm": 180,
    "weight_kg": 80,
    "activity_level": "moderate",
    "goal": "maintain",
    "timezone": "UTC",
}

#: Two eggs and a glass of milk. 100 g at 143 kcal + 257.5 g at 61 kcal.
BREAKFAST = {
    "name": "Petit-déjeuner",
    "items": [{"slug": "egg", "amount": 2}, {"slug": "milk", "amount": 250}],
}


def onboarded(client: TestClient, email: str = "cook@example.com") -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.put("/api/v1/profile", json=PROFILE, headers=headers)
    return headers


def test_composing_a_meal_sums_its_ingredients(client: TestClient, catalogue) -> None:
    headers = onboarded(client)

    response = client.post("/api/v1/meals", json=BREAKFAST, headers=headers)

    assert response.status_code == 201
    meal = response.json()
    assert meal["totals"]["total_grams"] == 357.5
    assert meal["totals"]["kcal"] == pytest.approx(300.08, abs=0.01)
    assert meal["totals"]["protein_g"] == pytest.approx(20.71, abs=0.01)


def test_each_ingredient_reports_its_own_contribution(client: TestClient, catalogue) -> None:
    """So the builder can show where the calories are coming from as you add."""
    headers = onboarded(client)

    meal = client.post("/api/v1/meals", json=BREAKFAST, headers=headers).json()

    egg, milk = meal["items"]
    assert egg["grams"] == 100.0
    assert egg["kcal"] == 143.0
    assert milk["grams"] == 257.5
    assert milk["amount"] == 250  # still millilitres to the user


def test_a_gap_in_one_ingredient_makes_the_total_partial(client: TestClient, catalogue) -> None:
    """The egg reports 0 g of fibre; the milk reports none at all.

    The sum is 0.0 either way, which is exactly why this needs flagging: an
    unflagged "0 g fibre" reads as a measurement, when half of it is a hole.
    """
    headers = onboarded(client)

    meal = client.post("/api/v1/meals", json=BREAKFAST, headers=headers).json()

    assert "fibre_g" in meal["totals"]["partial"]


def test_an_unknown_ingredient_is_rejected_before_anything_is_written(
    client: TestClient, catalogue
) -> None:
    headers = onboarded(client)

    response = client.post(
        "/api/v1/meals",
        json={"name": "Mystery", "items": [{"slug": "pangolin", "amount": 1}]},
        headers=headers,
    )

    assert response.status_code == 422
    assert "pangolin" in response.json()["detail"]
    assert client.get("/api/v1/meals", headers=headers).json() == []


def test_the_same_ingredient_twice_is_rejected(client: TestClient, catalogue) -> None:
    """Always a mis-tap. The user meant to change the amount on the row they had."""
    headers = onboarded(client)

    response = client.post(
        "/api/v1/meals",
        json={
            "name": "Eggs and eggs",
            "items": [{"slug": "egg", "amount": 1}, {"slug": "egg", "amount": 2}],
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_an_empty_meal_is_rejected(client: TestClient, catalogue) -> None:
    headers = onboarded(client)

    response = client.post("/api/v1/meals", json={"name": "Nothing", "items": []}, headers=headers)

    assert response.status_code == 422


def test_meals_are_private_to_their_owner(client: TestClient, catalogue) -> None:
    """The owner is part of the query, not a check after it."""
    mine = onboarded(client, "mine@example.com")
    theirs = onboarded(client, "theirs@example.com")
    meal_id = client.post("/api/v1/meals", json=BREAKFAST, headers=mine).json()["id"]

    assert client.get(f"/api/v1/meals/{meal_id}", headers=theirs).status_code == 404
    assert client.get("/api/v1/meals", headers=theirs).json() == []
    assert client.delete(f"/api/v1/meals/{meal_id}", headers=theirs).status_code == 404
    # And the owner still has it.
    assert client.get(f"/api/v1/meals/{meal_id}", headers=mine).status_code == 200


def test_a_malformed_id_is_a_404_not_a_500(client: TestClient, catalogue) -> None:
    """An unparseable ObjectId and a missing one are the same fact to the user."""
    headers = onboarded(client)

    assert client.get("/api/v1/meals/not-an-object-id", headers=headers).status_code == 404


def test_replacing_a_meal_returns_the_new_version(client: TestClient, catalogue) -> None:
    """Guards the driver default that returns the pre-update document — which
    would show the user the meal they just replaced."""
    headers = onboarded(client)
    meal_id = client.post("/api/v1/meals", json=BREAKFAST, headers=headers).json()["id"]

    updated = client.put(
        f"/api/v1/meals/{meal_id}",
        json={"name": "Just eggs", "items": [{"slug": "egg", "amount": 3}]},
        headers=headers,
    ).json()

    assert updated["name"] == "Just eggs"
    assert len(updated["items"]) == 1
    assert updated["totals"]["kcal"] == pytest.approx(214.5)


def test_logging_a_meal_writes_one_entry_with_the_summed_numbers(
    client: TestClient, catalogue
) -> None:
    """One entry, not one per ingredient — the plate is what the user built."""
    headers = onboarded(client)
    meal_id = client.post("/api/v1/meals", json=BREAKFAST, headers=headers).json()["id"]

    response = client.post(
        f"/api/v1/meals/{meal_id}/log", json={"meal_slot": "breakfast"}, headers=headers
    )

    assert response.status_code == 201
    entry = response.json()
    assert entry["food_name"] == "Petit-déjeuner"
    assert entry["quantity_grams"] == 357.5
    assert entry["kcal"] == pytest.approx(300.08, abs=0.01)

    day = client.get("/api/v1/diary", headers=headers).json()
    breakfast = next(m for m in day["meals"] if m["meal_slot"] == "breakfast")
    assert len(breakfast["entries"]) == 1


def test_editing_a_meal_does_not_rewrite_what_was_already_logged(
    client: TestClient, catalogue
) -> None:
    """The snapshot rule, at the meal level.

    Yesterday's breakfast is a record of what was eaten. Changing the meal
    definition today must not reach back and alter it.
    """
    headers = onboarded(client)
    meal_id = client.post("/api/v1/meals", json=BREAKFAST, headers=headers).json()["id"]
    client.post(f"/api/v1/meals/{meal_id}/log", json={"meal_slot": "breakfast"}, headers=headers)

    client.put(
        f"/api/v1/meals/{meal_id}",
        json={"name": "Just eggs", "items": [{"slug": "egg", "amount": 1}]},
        headers=headers,
    )

    day = client.get("/api/v1/diary", headers=headers).json()
    assert day["totals"]["kcal"] == pytest.approx(300.08, abs=0.01)


def test_deleting_a_meal_does_not_delete_its_history(client: TestClient, catalogue) -> None:
    headers = onboarded(client)
    meal_id = client.post("/api/v1/meals", json=BREAKFAST, headers=headers).json()["id"]
    client.post(f"/api/v1/meals/{meal_id}/log", json={"meal_slot": "breakfast"}, headers=headers)

    assert client.delete(f"/api/v1/meals/{meal_id}", headers=headers).status_code == 204

    day = client.get("/api/v1/diary", headers=headers).json()
    assert day["totals"]["kcal"] == pytest.approx(300.08, abs=0.01)


async def test_a_retired_ingredient_is_reported_not_silently_dropped(
    client: TestClient, catalogue, mongo
) -> None:
    """Mongo has no foreign keys, so this is the case Postgres used to prevent.

    Silently dropping the ingredient would make the meal's calories quietly fall;
    failing the read would make the meal unopenable. Reporting it lets the app say
    which ingredient went missing.
    """
    headers = onboarded(client)
    meal_id = client.post("/api/v1/meals", json=BREAKFAST, headers=headers).json()["id"]

    await mongo["food_items"].delete_one({"slug": "milk"})

    meal = client.get(f"/api/v1/meals/{meal_id}", headers=headers).json()

    assert meal["missing_slugs"] == ["milk"]
    assert len(meal["items"]) == 1
    assert meal["totals"]["kcal"] == 143.0


def test_meals_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/meals").status_code == 401
    assert client.post("/api/v1/meals", json=BREAKFAST).status_code == 401
