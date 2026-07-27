"""Gemini response normalisation.

These use recorded response *shapes* rather than hand-built dicts that match
what the parser expects. That distinction cost us a real bug once already: the
first USDA scaling test asserted the same wrong assumption the code made, so it
passed while the app reported a 975 kcal banana. A test written from the same
misunderstanding as the code cannot catch the misunderstanding.
"""

import json

import httpx
import pytest

from app.core.config import get_settings
from app.services.vision import (
    MAX_ITEM_GRAMS,
    MAX_OUTPUT_TOKENS,
    THINKING_BUDGET_TOKENS,
    VisionClient,
    VisionQuotaExhausted,
    VisionUnavailable,
    parse_vision_response,
)


@pytest.fixture
def gemini_key(monkeypatch) -> None:
    """Pretend a key is configured, so the client gets as far as the transport.

    No real key is ever needed here — every request is served by a mock — but
    without one `analyse_meal` short-circuits with VisionNotConfigured.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def gemini_response(payload: dict) -> dict:
    """Wrap a model JSON payload in the envelope generateContent really returns."""
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": json.dumps(payload)}], "role": "model"},
                "finishReason": "STOP",
                "index": 0,
            }
        ],
        "usageMetadata": {"promptTokenCount": 271, "candidatesTokenCount": 88},
        "modelVersion": "gemini-2.5-flash",
    }


def test_parses_a_normal_meal() -> None:
    result = parse_vision_response(
        gemini_response(
            {
                "items": [
                    {"name": "grilled chicken breast", "quantity_grams": 150, "confidence": 0.9},
                    {"name": "white rice cooked", "quantity_grams": 200, "confidence": 0.75},
                ],
                "notes": "Sauce not identifiable.",
            }
        )
    )

    assert [item.name for item in result.items] == [
        "grilled chicken breast",
        "white rice cooked",
    ]
    assert result.items[0].quantity_grams == 150
    assert result.notes == "Sauce not identifiable."


def test_no_food_in_photo_is_an_empty_list_not_an_error() -> None:
    """Photographing a keyboard is a normal outcome, not a failure.

    The app shows "no food detected" copy for this, so it must arrive as a valid
    empty result rather than an exception.
    """
    result = parse_vision_response(
        gemini_response({"items": [], "notes": "This photo shows a laptop, not food."})
    )

    assert result.items == []
    assert "laptop" in result.notes


def test_drops_malformed_items_and_keeps_the_rest() -> None:
    """One hallucinated entry must not cost the user the good ones."""
    result = parse_vision_response(
        gemini_response(
            {
                "items": [
                    {"name": "banana", "quantity_grams": 118, "confidence": 0.95},
                    {"name": "impossible", "quantity_grams": MAX_ITEM_GRAMS + 1, "confidence": 1},
                    {"name": "negative", "quantity_grams": -5, "confidence": 0.5},
                    {"name": "", "quantity_grams": 50, "confidence": 0.5},
                    {"name": "no confidence field", "quantity_grams": 50},
                    {"name": "oat milk", "quantity_grams": 240, "confidence": 0.6},
                ],
                "notes": "",
            }
        )
    )

    assert [item.name for item in result.items] == ["banana", "oat milk"]


def test_caps_the_item_count() -> None:
    """A model that splits one plate into twenty entries is not being useful."""
    result = parse_vision_response(
        gemini_response(
            {
                "items": [
                    {"name": f"item {n}", "quantity_grams": 10, "confidence": 0.5}
                    for n in range(30)
                ]
            }
        )
    )

    assert len(result.items) == 8


def test_missing_notes_field_is_fine() -> None:
    """`notes` is optional in the schema; absence must not raise."""
    result = parse_vision_response(
        gemini_response({"items": [{"name": "apple", "quantity_grams": 180, "confidence": 0.8}]})
    )

    assert result.notes == ""


def test_safety_block_raises_rather_than_returning_nothing() -> None:
    """A blocked response has candidates but no parts.

    Silently returning zero items here would show the user "no food detected",
    which is a lie about what happened.
    """
    blocked = {"candidates": [{"finishReason": "SAFETY", "index": 0}]}

    with pytest.raises(VisionUnavailable, match="SAFETY"):
        parse_vision_response(blocked)


def test_non_json_text_raises() -> None:
    """Schema-constrained output should never be prose, but if it is, say so."""
    payload = {"candidates": [{"content": {"parts": [{"text": "I cannot help with that."}]}}]}

    with pytest.raises(VisionUnavailable, match="invalid JSON"):
        parse_vision_response(payload)


def test_empty_response_raises() -> None:
    with pytest.raises(VisionUnavailable):
        parse_vision_response({})


def test_thinking_exhausting_the_budget_is_reported_not_swallowed() -> None:
    """The failure that made this flaky in the first place.

    Current flash models think before answering and those tokens come out of the
    same budget as the reply. When thinking uses all of it the candidate comes
    back with no `parts` at all — which must surface as an error, not as a
    cheerful "no food detected".
    """
    starved = {"candidates": [{"finishReason": "MAX_TOKENS", "index": 0}]}

    with pytest.raises(VisionUnavailable, match="MAX_TOKENS"):
        parse_vision_response(starved)


# --------------------------------------------------------------------------- #
# Transport: retries, and what must never be retried.
# --------------------------------------------------------------------------- #


class Upstream:
    """A stand-in Gemini that serves scripted responses and counts calls."""

    def __init__(self, *payloads: tuple[int, dict]) -> None:
        self._payloads = payloads
        self.calls = 0

    def _handle(self, request: httpx.Request) -> httpx.Response:
        # The last entry repeats, so a one-entry script means "always this".
        status, body = self._payloads[min(self.calls, len(self._payloads) - 1)]
        self.calls += 1
        return httpx.Response(status, json=body)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))


OVERLOADED = (503, {"error": "overloaded"})
OK = (200, gemini_response({"items": [], "notes": "nothing here"}))


async def test_retries_a_transient_upstream_error(gemini_key) -> None:
    """Google's own 503s appeared in roughly one call in three during testing.

    Without a retry each one becomes a failed scan the user sees.
    """
    upstream = Upstream(OVERLOADED, OK)
    async with upstream.client() as client:
        result = await VisionClient(client).analyse_meal("Zm9v", "image/jpeg")

    assert result.notes == "nothing here"
    assert upstream.calls == 2


async def test_gives_up_after_the_retry(gemini_key) -> None:
    upstream = Upstream(OVERLOADED)
    async with upstream.client() as client:
        with pytest.raises(VisionUnavailable, match="503"):
            await VisionClient(client).analyse_meal("Zm9v", "image/jpeg")

    assert upstream.calls == 2


async def test_never_retries_a_quota_error(gemini_key) -> None:
    """Retrying a spent quota just spends more of a budget shared with others."""
    upstream = Upstream((429, {"error": "quota"}))
    async with upstream.client() as client:
        with pytest.raises(VisionQuotaExhausted):
            await VisionClient(client).analyse_meal("Zm9v", "image/jpeg")

    assert upstream.calls == 1


async def test_never_retries_a_retired_model(gemini_key) -> None:
    """Google reports a model retired for new keys as 404, not 400.

    It is permanent, so a retry only doubles the latency before the same error.
    """
    upstream = Upstream((404, {"error": {"message": "no longer available"}}))
    async with upstream.client() as client:
        with pytest.raises(VisionUnavailable, match="404"):
            await VisionClient(client).analyse_meal("Zm9v", "image/jpeg")

    assert upstream.calls == 1


async def test_request_budgets_room_for_the_answer_after_thinking(gemini_key) -> None:
    """Guards the fix: thinking is capped strictly below the total budget."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=gemini_response({"items": []}))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await VisionClient(client).analyse_meal("Zm9v", "image/jpeg")

    config = captured["generationConfig"]  # type: ignore[index]
    assert config["max_output_tokens"] == MAX_OUTPUT_TOKENS
    assert config["thinkingConfig"]["thinkingBudget"] == THINKING_BUDGET_TOKENS
    assert THINKING_BUDGET_TOKENS < MAX_OUTPUT_TOKENS
