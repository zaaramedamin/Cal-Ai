"""Describing a meal in words instead of photographing it.

The point of these is that the text path is not a *shortcut*. It must reach the
same matching pipeline as a photo — USDA first, cache second, AI estimate only
if both fail — because a second path is a second place an invented calorie could
enter the system.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.v1.scan import get_vision_client
from app.main import app
from app.services.vision import VisionItem, VisionResult


class StubVision:
    """Records what it was asked, returns what the test wants."""

    def __init__(self, result: VisionResult) -> None:
        self.result = result
        self.described: list[str] = []
        self.analysed = 0

    async def describe_meal(self, description: str) -> VisionResult:
        self.described.append(description)
        return self.result

    async def analyse_meal(self, image_base64: str, media_type: str) -> VisionResult:
        self.analysed += 1
        return self.result

    async def estimate_nutrition(self, names: list[str]) -> dict[str, Any]:
        # Empty: these tests assert on matching, and an estimate arriving here
        # would mean the food was not found — which the assertions check for.
        return {}


@pytest.fixture
def stub_vision():
    stub = StubVision(
        VisionResult(
            items=[
                VisionItem(
                    name="two boiled eggs",
                    search_term="egg",
                    quantity_grams=100,
                    confidence=0.9,
                )
            ],
            notes="",
        )
    )
    app.dependency_overrides[get_vision_client] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_vision_client, None)


def onboarded(client: TestClient, email: str = "describe@example.com") -> dict[str, str]:
    registered = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    client.put(
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
    return headers


def test_a_description_is_sent_to_the_model(client, stub_vision, catalogue) -> None:
    headers = onboarded(client)

    response = client.post(
        "/api/v1/scan/describe", headers=headers, json={"description": "two boiled eggs"}
    )

    assert response.status_code == 200, response.text
    assert stub_vision.described == ["two boiled eggs"]
    # The photo path was never touched — no image was invented to satisfy it.
    assert stub_vision.analysed == 0


def test_described_foods_are_matched_against_the_database(client, stub_vision, catalogue) -> None:
    """The whole point: text goes through the same matcher as a photo, so the
    numbers come from the food database and not from the model."""
    headers = onboarded(client, "matched@example.com")

    body = client.post(
        "/api/v1/scan/describe", headers=headers, json={"description": "two boiled eggs"}
    ).json()

    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["detected_name"] == "two boiled eggs"
    assert item["estimated_grams"] == 100
    # Matched to a real food, so nothing was estimated.
    assert item["match"] is not None
    assert body["estimated_count"] == 0


def test_an_empty_description_is_refused(client, stub_vision) -> None:
    headers = onboarded(client, "empty@example.com")

    assert (
        client.post("/api/v1/scan/describe", headers=headers, json={"description": ""}).status_code
        == 422
    )


def test_a_very_long_description_is_refused(client, stub_vision) -> None:
    """Bounded so the endpoint cannot be used as a general-purpose prompt into a
    shared Gemini budget."""
    headers = onboarded(client, "long@example.com")

    response = client.post(
        "/api/v1/scan/describe", headers=headers, json={"description": "rice " * 200}
    )
    assert response.status_code == 422


def test_describing_needs_authentication(client, stub_vision) -> None:
    assert client.post("/api/v1/scan/describe", json={"description": "an egg"}).status_code == 401
