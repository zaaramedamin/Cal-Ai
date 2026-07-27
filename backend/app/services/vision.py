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

import asyncio
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

#: Current flash models think before answering, and those thinking tokens are
#: charged against the same output budget as the reply. Observed usage on a
#: simple photo is ~200 thinking tokens against ~30 of answer, but a crowded
#: plate reasons for longer — and if thinking exhausts the budget the response
#: comes back with `finishReason: MAX_TOKENS` and *no content at all*, which
#: looks exactly like a server fault. Budget generously in both directions: the
#: cap is a safety net, not a target, and unused tokens cost nothing.
MAX_OUTPUT_TOKENS = 4096
THINKING_BUDGET_TOKENS = 1024

#: Google's own infrastructure returns transient 503s under load — one appeared
#: in roughly one call in three while testing this. Retrying once turns a blip
#: into a slightly slower scan instead of a failure the user sees.
MAX_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 1.5
RETRYABLE_STATUS = frozenset({500, 502, 503, 504})

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
        # Covers finishReason=SAFETY and =MAX_TOKENS, both of which return a
        # candidate with no parts. MAX_TOKENS here means thinking ate the whole
        # budget — see MAX_OUTPUT_TOKENS above.
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
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                # Some thinking genuinely helps on a crowded plate, so it stays
                # on — but capped, so it can never consume the whole budget and
                # leave no room for the answer.
                "thinkingConfig": {"thinkingBudget": THINKING_BUDGET_TOKENS},
            },
        }

        url = f"{BASE_URL}/models/{settings.gemini_model}:generateContent"
        client = self._client or httpx.AsyncClient(timeout=40.0)
        try:
            return await self._post_with_retry(client, url, body, settings.gemini_api_key)
        finally:
            if self._client is None:
                await client.aclose()

    async def _post_with_retry(
        self, client: httpx.AsyncClient, url: str, body: dict[str, Any], api_key: str
    ) -> VisionResult:
        """POST once, retrying only failures that a retry can plausibly fix.

        Deliberately narrow. A 429 is a spent quota and retrying makes it worse;
        a 400 is our bug and will fail identically. Only transient upstream
        faults and connection errors are worth a second attempt.
        """
        last_error: Exception | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await client.post(
                    url,
                    json=body,
                    # Key goes in a header, not the query string — query strings
                    # end up in proxy and server logs.
                    headers={"x-goog-api-key": api_key},
                )
            except httpx.HTTPError as exc:
                last_error = VisionUnavailable("Could not reach Gemini")
                logger.warning("Gemini request failed (attempt %d): %s", attempt, exc)
            else:
                if response.status_code == 429:
                    # The shared free-tier budget for the day/minute is spent.
                    raise VisionQuotaExhausted("Gemini free-tier quota exhausted")

                if response.status_code not in RETRYABLE_STATUS:
                    if not response.is_success:
                        # A 404 here usually means the configured model is
                        # retired for this API key — Google reports that as
                        # "no longer available to new users", not as a 400.
                        logger.warning(
                            "Gemini returned %s: %s",
                            response.status_code,
                            response.text[:300],
                        )
                        raise VisionUnavailable(f"Gemini returned {response.status_code}")
                    return parse_vision_response(response.json())

                last_error = VisionUnavailable(f"Gemini returned {response.status_code}")
                logger.warning(
                    "Gemini returned %s (attempt %d of %d)",
                    response.status_code,
                    attempt,
                    MAX_ATTEMPTS,
                )

            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)

        raise last_error or VisionUnavailable("Gemini request failed")
