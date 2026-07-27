"""The scan endpoint: photo in, USDA-matched foods out.

Every test here uses a fake vision client. Nothing touches Gemini, so the suite
stays fast, deterministic, and free — and the assertions are about *our*
pipeline, which is what these tests are for.
"""

import base64
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.scan import get_vision_client
from app.db.models.food import Food
from app.main import app
from app.services.vision import (
    VisionItem,
    VisionNotConfigured,
    VisionQuotaExhausted,
    VisionResult,
    VisionUnavailable,
)

# A tiny valid base64 blob. The endpoint checks the encoding, not the pixels —
# the fake vision client never looks at it.
IMAGE = base64.b64encode(b"x" * 512).decode()


def authed(client: TestClient, email: str = "scan@example.com") -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class FakeVision:
    """Stands in for Gemini. Returns a canned result or raises."""

    def __init__(self, result: VisionResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls = 0

    async def analyse_meal(self, image_base64: str, media_type: str) -> VisionResult:
        self.calls += 1
        if self._error:
            raise self._error
        assert self._result is not None
        return self._result


@pytest.fixture
def use_vision() -> Iterator[list[FakeVision]]:
    """Install a fake vision client; yields a list to hold the one in use."""
    installed: list[FakeVision] = []

    def install(fake: FakeVision) -> FakeVision:
        installed.append(fake)
        app.dependency_overrides[get_vision_client] = lambda: fake
        return fake

    yield install  # type: ignore[misc]
    app.dependency_overrides.pop(get_vision_client, None)


async def seed_food(session: AsyncSession, name: str, **overrides) -> Food:
    food = Food(
        source="usda",
        source_id=overrides.pop("source_id", name),
        name=name,
        kcal=overrides.pop("kcal", 165),
        protein_g=overrides.pop("protein_g", 31),
        carbs_g=overrides.pop("carbs_g", 0),
        fat_g=overrides.pop("fat_g", 3.6),
        **overrides,
    )
    session.add(food)
    await session.commit()
    await session.refresh(food)
    return food


async def test_detected_foods_are_matched_to_real_database_rows(
    client: TestClient, session: AsyncSession, use_vision
) -> None:
    """The core claim: nutrition comes from the cache, not from the model."""
    await seed_food(session, "Chicken breast, grilled", kcal=165, protein_g=31)
    use_vision(
        FakeVision(
            VisionResult(
                items=[
                    VisionItem(name="chicken breast", quantity_grams=150, confidence=0.9),
                ],
                notes="Looks grilled.",
            )
        )
    )

    response = client.post(
        "/api/v1/scan",
        json={"image_base64": IMAGE, "media_type": "image/jpeg"},
        headers=authed(client),
    )

    assert response.status_code == 200
    body = response.json()
    item = body["items"][0]

    # What the model said.
    assert item["detected_name"] == "chicken breast"
    assert item["estimated_grams"] == 150
    # What the database said — note these are the seeded per-100 g values,
    # untouched by the model.
    assert item["match"]["name"] == "Chicken breast, grilled"
    assert item["match"]["kcal"] == 165
    assert item["match"]["protein_g"] == 31
    assert body["notes"] == "Looks grilled."
    assert body["unmatched_count"] == 0


async def test_unmatched_items_carry_no_nutrition(
    client: TestClient, session: AsyncSession, use_vision, monkeypatch
) -> None:
    """A food we cannot match is reported honestly, never invented.

    USDA is stubbed out so the miss is deterministic — otherwise this test would
    depend on what a live search returns for a nonsense word.
    """

    async def no_upstream(*args, **kwargs):
        return []

    monkeypatch.setattr("app.services.food_cache.UsdaClient.search", no_upstream)
    use_vision(
        FakeVision(
            VisionResult(items=[VisionItem(name="zzzznotafood", quantity_grams=90, confidence=0.3)])
        )
    )

    response = client.post("/api/v1/scan", json={"image_base64": IMAGE}, headers=authed(client))

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["match"] is None
    assert body["unmatched_count"] == 1


async def test_no_food_in_photo_returns_an_empty_list(client: TestClient, use_vision) -> None:
    use_vision(FakeVision(VisionResult(items=[], notes="No food visible.")))

    response = client.post("/api/v1/scan", json={"image_base64": IMAGE}, headers=authed(client))

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["notes"] == "No food visible."


async def test_missing_api_key_is_503_with_instructions(client: TestClient, use_vision) -> None:
    """The feature being off is an operator problem, not a server fault."""
    use_vision(FakeVision(error=VisionNotConfigured("no key")))

    response = client.post("/api/v1/scan", json={"image_base64": IMAGE}, headers=authed(client))

    assert response.status_code == 503
    assert "aistudio.google.com" in response.json()["detail"]


async def test_quota_exhausted_is_429_with_retry_after(client: TestClient, use_vision) -> None:
    use_vision(FakeVision(error=VisionQuotaExhausted("spent")))

    response = client.post("/api/v1/scan", json={"image_base64": IMAGE}, headers=authed(client))

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "3600"


async def test_upstream_failure_is_502(client: TestClient, use_vision) -> None:
    use_vision(FakeVision(error=VisionUnavailable("network")))

    response = client.post("/api/v1/scan", json={"image_base64": IMAGE}, headers=authed(client))

    assert response.status_code == 502


async def test_requires_authentication(client: TestClient) -> None:
    """Scanning spends a shared, finite quota — never leave it open."""
    response = client.post("/api/v1/scan", json={"image_base64": IMAGE})

    assert response.status_code == 401


async def test_rejects_invalid_base64_without_spending_quota(
    client: TestClient, use_vision
) -> None:
    """Malformed input must fail locally, before a request leaves the building."""
    fake = FakeVision(VisionResult(items=[]))
    use_vision(fake)

    response = client.post(
        "/api/v1/scan",
        json={"image_base64": "!!!! not base64 !!!!" * 10},
        headers=authed(client),
    )

    assert response.status_code == 422
    assert fake.calls == 0


async def test_rejects_unknown_media_type(client: TestClient, use_vision) -> None:
    use_vision(FakeVision(VisionResult(items=[])))

    response = client.post(
        "/api/v1/scan",
        json={"image_base64": IMAGE, "media_type": "application/pdf"},
        headers=authed(client),
    )

    assert response.status_code == 422


async def test_rate_limit_protects_the_shared_quota(
    client: TestClient, use_vision, rate_limited
) -> None:
    """Twenty an hour, then a 429 — before Gemini is asked a twenty-first time."""
    fake = FakeVision(VisionResult(items=[]))
    use_vision(fake)
    headers = authed(client)

    for _ in range(20):
        assert (
            client.post("/api/v1/scan", json={"image_base64": IMAGE}, headers=headers).status_code
            == 200
        )

    blocked = client.post("/api/v1/scan", json={"image_base64": IMAGE}, headers=headers)

    assert blocked.status_code == 429
    assert fake.calls == 20
