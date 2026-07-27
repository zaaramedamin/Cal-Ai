"""Meal photo analysis via Google Gemini.

**What the AI is allowed to do here — and what it is not.**

This app's core rule is that no nutrition value is ever invented, and a vision
model guessing "roughly 620 kcal" from a photo is exactly that. So the model's
job is deliberately narrow: name the foods in the photo and estimate portion
sizes in grams. The nutrition numbers then come from our USDA-backed database,
and the user confirms or corrects everything on a review screen before logging.
The AI proposes; USDA prices; the user decides.

The backend proxies Gemini for the same reasons it proxies USDA (see
`services/usda.py`): the key must not ship in a mobile bundle, the free tier is
a shared budget (~250 requests/day) that needs server-side stewardship, and
normalising the response server-side means a Gemini shape change is a backend
fix rather than an app-store release.

Photos are analyzed and discarded — nothing is persisted server-side.
"""

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

#: Upper bound on a single detected portion. A 3 kg item on one plate is a
#: hallucination, not a meal.
MAX_ITEM_GRAMS = 3000

#: More than this is the model splitting hairs ("rice", "rice grains", ...).
MAX_ITEMS = 8


class VisionUnavailable(RuntimeError):
    """Gemini could not be reached or answered with a server error."""


class VisionQuotaExhausted(RuntimeError):
    """The free-tier quota is spent; try again later."""


class VisionNotConfigured(RuntimeError):
    """No API key is configured; the feature is off."""


class VisionItem(BaseModel):
    """One food the model saw, with its portion estimate.

    Note what is absent: no calories, no macros. The model is never asked for
    nutrition numbers, so it cannot smuggle invented ones into the pipeline.
    """

    name: str = Field(min_length=1, max_length=80)
    quantity_grams: float = Field(gt=0, le=MAX_ITEM_GRAMS)
    #: The model's own certainty, 0..1. Shown to the user as a hint, never used
    #: to auto-log anything.
    confidence: float = Field(ge=0, le=1)


class VisionResult(BaseModel):
    items: list[VisionItem]
    #: Free-text caveats from the model ("sauce not visible", "partially eaten").
    notes: str = ""


#: Gemini structured-output schema. Mirrors VisionItem — the model is
#: constrained to this shape server-side, which eliminates most parse failures.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "quantity_grams": {"type": "NUMBER"},
                    "confidence": {"type": "NUMBER"},
                },
                "required": ["name", "quantity_grams", "confidence"],
            },
        },
        "notes": {"type": "STRING"},
    },
    "required": ["items"],
}

PROMPT = """\
You are a nutrition assistant analysing a photo of food.

Identify each distinct edible item visible and estimate its weight in grams as
served. Rules:

- Use plain, generic food names that would match a food database search:
  "grilled chicken breast", "white rice cooked", "broccoli steamed" — never
  brand names, never dish poetry.
- Estimate quantity_grams from visual cues (plate size, utensils, thickness).
  These are estimates the user will adjust; be realistic, not precise.
- confidence is 0 to 1: how sure you are of BOTH the identification and the
  portion. Sauces and hidden ingredients deserve low confidence.
- List at most 8 items. Merge duplicates. Ignore garnish under ~5 g.
- If the photo contains no food, return an empty items list and say why in
  notes.
- Do NOT estimate calories or nutrients. Only names and gram weights.
"""


def parse_vision_response(payload: dict[str, Any]) -> VisionResult:
    """Extract and validate the model's JSON from a generateContent response.

    Malformed items are dropped individually rather than failing the scan: one
    hallucinated 5 kg entry should not cost the user the four good ones.
    """
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        # Includes the finishReason=SAFETY case, where parts is absent.
        reason = (payload.get("candidates") or [{}])[0].get("finishReason", "unknown")
        raise VisionUnavailable(f"Gemini returned no content (finishReason={reason})") from exc

    import json

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VisionUnavailable("Gemini returned invalid JSON despite schema") from exc

    items: list[VisionItem] = []
    for entry in (raw.get("items") or [])[:MAX_ITEMS]:
        try:
            items.append(VisionItem.model_validate(entry))
        except ValidationError:
            logger.warning("Dropping malformed vision item: %r", entry)

    notes = raw.get("notes") or ""
    return VisionResult(items=items, notes=str(notes)[:500])


class VisionClient:
    """Thin async wrapper over Gemini generateContent."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def analyse_meal(self, image_base64: str, media_type: str) -> VisionResult:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise VisionNotConfigured(
                "GEMINI_API_KEY is not set. Get a free key at aistudio.google.com/apikey"
            )

        body = {
            "contents": [
                {
                    "parts": [
                        {"inline_data": {"mime_type": media_type, "data": image_base64}},
                        {"text": PROMPT},
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": RESPONSE_SCHEMA,
                # Deterministic-ish output suits an extraction task; Gemini
                # still accepts temperature, unlike current Claude models.
                "temperature": 0.2,
                "max_output_tokens": 1024,
            },
        }

        url = f"{BASE_URL}/models/{settings.gemini_model}:generateContent"
        client = self._client or httpx.AsyncClient(timeout=40.0)
        try:
            response = await client.post(
                url,
                json=body,
                # Key goes in a header, not the query string — query strings
                # end up in proxy and server logs.
                headers={"x-goog-api-key": settings.gemini_api_key},
            )
            if response.status_code == 429:
                # The shared free-tier budget for the day/minute is spent.
                raise VisionQuotaExhausted("Gemini free-tier quota exhausted")
            response.raise_for_status()
            return parse_vision_response(response.json())
        except (VisionQuotaExhausted, VisionUnavailable):
            raise
        except httpx.HTTPStatusError as exc:
            logger.warning("Gemini responded %s", exc.response.status_code)
            raise VisionUnavailable(f"Gemini returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            logger.warning("Gemini request failed: %s", exc)
            raise VisionUnavailable("Could not reach Gemini") from exc
        finally:
            if self._client is None:
                await client.aclose()
