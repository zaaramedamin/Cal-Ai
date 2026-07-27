"""Profile, targets and weight endpoints."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.v1.profile import age_on

VALID_PROFILE = {
    "sex": "male",
    "birth_date": "1996-05-20",
    "height_cm": 180,
    "weight_kg": 80,
    "activity_level": "moderate",
    "goal": "maintain",
    "timezone": "Europe/Paris",
}


def auth_headers(client: TestClient, email: str = "profile@example.com") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# --------------------------------------------------------------------------- #
# age_on
# --------------------------------------------------------------------------- #


def test_age_the_day_before_a_birthday() -> None:
    """The off-by-one everyone writes at least once."""
    assert age_on(date(2000, 3, 1), date(2026, 2, 28)) == 25


def test_age_on_the_birthday() -> None:
    assert age_on(date(2000, 3, 1), date(2026, 3, 1)) == 26


def test_age_the_day_after_a_birthday() -> None:
    assert age_on(date(2000, 3, 1), date(2026, 3, 2)) == 26


def test_age_for_a_leap_day_birth() -> None:
    """Born 29 February. On 28 February of a non-leap year they are not yet older."""
    assert age_on(date(2000, 2, 29), date(2026, 2, 28)) == 25
    assert age_on(date(2000, 2, 29), date(2026, 3, 1)) == 26


# --------------------------------------------------------------------------- #
# Onboarding
# --------------------------------------------------------------------------- #


def test_profile_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/profile").status_code == 401
    assert client.put("/api/v1/profile", json=VALID_PROFILE).status_code == 401


def test_profile_is_404_before_onboarding(client: TestClient) -> None:
    assert client.get("/api/v1/profile", headers=auth_headers(client)).status_code == 404


def test_onboarding_returns_targets(client: TestClient) -> None:
    headers = auth_headers(client)
    response = client.put("/api/v1/profile", json=VALID_PROFILE, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["goal"] == "maintain"
    assert body["current_weight_kg"] == 80
    assert body["targets"]["calories"] > 0
    assert body["targets"]["macros"]["protein_g"] > 0
    assert body["targets"]["derivation"], "the explanation must ship with the numbers"


def test_onboarding_is_idempotent(client: TestClient) -> None:
    """PUT twice leaves the same state — the app never has to ask whether a
    profile already exists."""
    headers = auth_headers(client)
    first = client.put("/api/v1/profile", json=VALID_PROFILE, headers=headers).json()
    second = client.put("/api/v1/profile", json=VALID_PROFILE, headers=headers).json()

    assert first["targets"]["calories"] == second["targets"]["calories"]
    assert (
        first["profile"]["onboarding_completed_at"]
        == second["profile"]["onboarding_completed_at"]
    ), "the original completion time must not be overwritten by an edit"


def test_profile_can_be_read_back(client: TestClient) -> None:
    headers = auth_headers(client)
    client.put("/api/v1/profile", json=VALID_PROFILE, headers=headers)

    body = client.get("/api/v1/profile", headers=headers).json()
    assert body["profile"]["height_cm"] == 180
    assert body["profile"]["timezone"] == "Europe/Paris"


def test_changing_goal_changes_the_target(client: TestClient) -> None:
    headers = auth_headers(client)
    maintaining = client.put("/api/v1/profile", json=VALID_PROFILE, headers=headers).json()
    cutting = client.put(
        "/api/v1/profile", json={**VALID_PROFILE, "goal": "cut"}, headers=headers
    ).json()

    assert cutting["targets"]["calories"] < maintaining["targets"]["calories"]
    assert cutting["targets"]["macros"]["protein_g"] > maintaining["targets"]["macros"]["protein_g"]


def test_profiles_are_isolated_between_users(client: TestClient) -> None:
    """The check that matters most: one user must never see another's data."""
    alice = auth_headers(client, "alice@example.com")
    bob = auth_headers(client, "bob@example.com")

    client.put("/api/v1/profile", json=VALID_PROFILE, headers=alice)

    assert client.get("/api/v1/profile", headers=bob).status_code == 404


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "override",
    [
        {"height_cm": 17},
        {"height_cm": 300},
        {"weight_kg": 5},
        {"weight_kg": 500},
        {"sex": "other"},
        {"activity_level": "extreme"},
        {"goal": "shred"},
    ],
)
def test_invalid_profile_input_is_rejected(client: TestClient, override: dict) -> None:
    response = client.put(
        "/api/v1/profile", json={**VALID_PROFILE, **override}, headers=auth_headers(client)
    )
    assert response.status_code == 422


def test_future_birth_date_is_rejected(client: TestClient) -> None:
    future = (date.today() + timedelta(days=1)).isoformat()
    response = client.put(
        "/api/v1/profile",
        json={**VALID_PROFILE, "birth_date": future},
        headers=auth_headers(client),
    )
    assert response.status_code == 422


def test_under_thirteen_is_rejected(client: TestClient) -> None:
    recent = (date.today() - timedelta(days=365 * 10)).isoformat()
    response = client.put(
        "/api/v1/profile",
        json={**VALID_PROFILE, "birth_date": recent},
        headers=auth_headers(client),
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Weight
# --------------------------------------------------------------------------- #


def test_onboarding_records_the_first_weight(client: TestClient) -> None:
    headers = auth_headers(client)
    client.put("/api/v1/profile", json=VALID_PROFILE, headers=headers)

    entries = client.get("/api/v1/profile/weight", headers=headers).json()
    assert len(entries) == 1
    assert entries[0]["weight_kg"] == 80


def test_logging_weight_twice_in_a_day_replaces_rather_than_appends(
    client: TestClient,
) -> None:
    """Two readings on one day describe hydration, not progress. Keeping both
    would put a meaningless spike in the trend chart."""
    headers = auth_headers(client)
    client.put("/api/v1/profile", json=VALID_PROFILE, headers=headers)

    client.post("/api/v1/profile/weight", json={"weight_kg": 79.5}, headers=headers)
    client.post("/api/v1/profile/weight", json={"weight_kg": 79.2}, headers=headers)

    entries = client.get("/api/v1/profile/weight", headers=headers).json()
    assert len(entries) == 1
    assert entries[0]["weight_kg"] == 79.2


def test_new_weight_changes_the_targets(client: TestClient) -> None:
    """Targets are recomputed on read, so they follow the latest weight
    automatically rather than going stale."""
    headers = auth_headers(client)
    original = client.put("/api/v1/profile", json=VALID_PROFILE, headers=headers).json()

    client.post("/api/v1/profile/weight", json={"weight_kg": 74}, headers=headers)
    updated = client.get("/api/v1/profile", headers=headers).json()

    assert updated["current_weight_kg"] == 74
    assert updated["targets"]["calories"] != original["targets"]["calories"]
    assert updated["targets"]["macros"]["protein_g"] < original["targets"]["macros"]["protein_g"]


def test_future_weight_dates_are_rejected(client: TestClient) -> None:
    headers = auth_headers(client)
    client.put("/api/v1/profile", json=VALID_PROFILE, headers=headers)

    future = (date.today() + timedelta(days=2)).isoformat()
    response = client.post(
        "/api/v1/profile/weight", json={"weight_kg": 79, "recorded_on": future}, headers=headers
    )
    assert response.status_code == 422


def test_weight_requires_a_profile(client: TestClient) -> None:
    response = client.post(
        "/api/v1/profile/weight", json={"weight_kg": 79}, headers=auth_headers(client)
    )
    assert response.status_code == 404
