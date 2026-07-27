"""Gemini response normalisation.

These use recorded response *shapes* rather than hand-built dicts that match
what the parser expects. That distinction cost us a real bug once already: the
first USDA scaling test asserted the same wrong assumption the code made, so it
passed while the app reported a 975 kcal banana. A test written from the same
misunderstanding as the code cannot catch the misunderstanding.
"""

import json

import pytest

from app.services.vision import MAX_ITEM_GRAMS, VisionUnavailable, parse_vision_response


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
