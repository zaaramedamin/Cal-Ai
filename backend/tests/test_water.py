"""Water tracking.

The interesting cases are not "logging works". They are: that a total is the
server's arithmetic and not the client's, that one user cannot touch another's
entries, and that no target is invented when the user has not set one.
"""

from fastapi.testclient import TestClient


def onboarded(client: TestClient, email: str = "thirsty@example.com") -> dict[str, str]:
    """An account past onboarding, which water needs for the timezone."""
    registered = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    assert registered.status_code == 201, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    profile = client.put(
        "/api/v1/profile",
        headers=headers,
        json={
            "sex": "male",
            "birth_date": "1996-05-20",
            "height_cm": 180,
            "weight_kg": 75,
            "activity_level": "moderate",
            "goal": "maintain",
            "target_weight_kg": None,
            "timezone": "Europe/Paris",
        },
    )
    assert profile.status_code in (200, 201), profile.text
    return headers


def test_a_day_starts_empty_with_no_invented_goal(client: TestClient) -> None:
    """The null goal is the point.

    Every "drink two litres a day" figure is a rule of thumb. Printing one as
    *your* target would be the same class of mistake as inventing a calorie
    value, so the day reports no goal until the user sets one.
    """
    headers = onboarded(client)

    body = client.get("/api/v1/water", headers=headers).json()

    assert body["total_ml"] == 0
    assert body["goal_ml"] is None
    assert body["entries"] == []


def test_logging_returns_the_whole_day_not_just_the_entry(client: TestClient) -> None:
    """So the client never has to do its own arithmetic and disagree with us."""
    headers = onboarded(client, "sum@example.com")

    client.post("/api/v1/water", headers=headers, json={"millilitres": 250})
    body = client.post("/api/v1/water", headers=headers, json={"millilitres": 330}).json()

    assert body["total_ml"] == 580
    assert len(body["entries"]) == 2


def test_an_entry_can_be_undone(client: TestClient) -> None:
    """Why this is a table of drinks rather than a counter: a mistaken tap has to
    be removable, and subtracting from a total cannot tell a mistake from a
    correction."""
    headers = onboarded(client, "undo@example.com")

    day = client.post("/api/v1/water", headers=headers, json={"millilitres": 500}).json()
    entry_id = day["entries"][0]["id"]

    assert client.delete(f"/api/v1/water/{entry_id}", headers=headers).status_code == 204
    assert client.get("/api/v1/water", headers=headers).json()["total_ml"] == 0


def test_one_user_cannot_delete_anothers_entry(client: TestClient) -> None:
    """The owner filter is part of the DELETE statement, not a check after it."""
    mine = onboarded(client, "owner@example.com")
    theirs = onboarded(client, "stranger@example.com")

    day = client.post("/api/v1/water", headers=mine, json={"millilitres": 400}).json()
    entry_id = day["entries"][0]["id"]

    assert client.delete(f"/api/v1/water/{entry_id}", headers=theirs).status_code == 404
    # And it is still there.
    assert client.get("/api/v1/water", headers=mine).json()["total_ml"] == 400


def test_an_implausible_amount_is_refused_with_a_422(client: TestClient) -> None:
    """Bounded because water intoxication is real, and because a typo'd 25000
    would otherwise render as a plausible-looking day rather than a mistake.

    A 422 rather than the 500 a raw constraint violation would produce — the
    database is the guarantee, the schema is the message."""
    headers = onboarded(client, "toomuch@example.com")

    assert (
        client.post("/api/v1/water", headers=headers, json={"millilitres": 25_000}).status_code
        == 422
    )
    assert (
        client.post("/api/v1/water", headers=headers, json={"millilitres": 0}).status_code == 422
    )


def test_water_cannot_be_logged_in_the_future(client: TestClient) -> None:
    headers = onboarded(client, "future@example.com")

    response = client.post(
        "/api/v1/water", headers=headers, json={"millilitres": 250, "day": "2099-01-01"}
    )
    assert response.status_code == 422


def test_a_goal_can_be_set_and_cleared(client: TestClient) -> None:
    """Clearing is a real choice, not a missing value — so null is accepted."""
    headers = onboarded(client, "goal@example.com")

    set_to = client.put("/api/v1/water/goal", headers=headers, json={"goal_ml": 2500}).json()
    assert set_to["goal_ml"] == 2500

    cleared = client.put("/api/v1/water/goal", headers=headers, json={"goal_ml": None}).json()
    assert cleared["goal_ml"] is None


def test_history_totals_by_day(client: TestClient) -> None:
    headers = onboarded(client, "history@example.com")

    client.post("/api/v1/water", headers=headers, json={"millilitres": 250})
    client.post("/api/v1/water", headers=headers, json={"millilitres": 250})

    history = client.get("/api/v1/water/history", headers=headers).json()

    assert len(history) == 1
    assert history[0]["total_ml"] == 500


def test_water_needs_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/water").status_code == 401
    assert client.post("/api/v1/water", json={"millilitres": 250}).status_code == 401
