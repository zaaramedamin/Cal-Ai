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
import json
import logging
import re
from collections.abc import Callable
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
    """The free-tier quota is spent.

    Carries what Google actually said rather than a guess. The first version of
    this hardcoded a one-hour wait for every 429, which produced the worst
    possible message: a user who had scanned nothing was told the daily
    allowance was gone and to come back in an hour, when the real answer was
    "about 40 seconds". Being wrong in that direction is worse than saying
    nothing — it teaches people the feature is broken.
    """

    def __init__(
        self, message: str, *, retry_after_seconds: int, daily_limit: int | None = None
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        #: The free-tier cap, when Google names one. Lets the app say "20 scans a
        #: day" instead of the vague "allowance", which sounds like a punishment.
        self.daily_limit = daily_limit


#: Fallback wait when Google's 429 carries no RetryInfo. A minute, not an hour:
#: a short wrong guess costs one retry, a long one costs the user the feature.
DEFAULT_QUOTA_RETRY_SECONDS = 60

_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')


def _quota_error(payload: dict[str, Any], raw: str) -> VisionQuotaExhausted:
    """Turn Google's 429 into something the app can tell the user honestly.

    Google puts the wait in a `RetryInfo` detail and the cap in a `QuotaFailure`
    violation. Both are worth extracting: the wait makes the message actionable,
    and the cap makes it explicable.
    """
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    retry_after = DEFAULT_QUOTA_RETRY_SECONDS
    daily_limit: int | None = None

    for detail in error.get("details", []):
        if str(detail.get("@type", "")).endswith("RetryInfo"):
            match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(detail.get("retryDelay", "")))
            if match:
                # Rounded up: telling someone to retry at the exact boundary
                # just earns them a second 429.
                retry_after = int(float(match.group(1))) + 1
        for violation in detail.get("violations", []):
            value = violation.get("quotaValue")
            if value is not None and str(value).isdigit():
                daily_limit = int(value)

    if retry_after == DEFAULT_QUOTA_RETRY_SECONDS:
        # Some responses carry the delay only in the prose message.
        fallback = _RETRY_DELAY.search(raw)
        if fallback:
            retry_after = int(float(fallback.group(1))) + 1

    return VisionQuotaExhausted(
        error.get("message", "Gemini quota exhausted"),
        retry_after_seconds=retry_after,
        daily_limit=daily_limit,
    )


class VisionNotConfigured(RuntimeError):
    """No API key is configured; the feature is off."""


class VisionItem(BaseModel):
    """One food the model saw, with its portion estimate.

    Note what is absent: no calories, no macros. The model is never asked for
    nutrition numbers, so it cannot smuggle invented ones into the pipeline.
    """

    name: str = Field(min_length=1, max_length=80)
    #: The same food stripped to its plainest form — "chicken breast" rather than
    #: "grilled chicken breast". Food databases file things formally, so the
    #: descriptive name a user recognises is a poor search key while the bare
    #: noun is a good one. Asking the model for both costs nothing and it knows
    #: which words are the food and which are the cooking.
    search_term: str = Field(default="", max_length=80)
    quantity_grams: float = Field(gt=0, le=MAX_ITEM_GRAMS)
    #: The model's own certainty, 0..1. Shown to the user as a hint, never used
    #: to auto-log anything.
    confidence: float = Field(ge=0, le=1)

    @property
    def query(self) -> str:
        """What to search the food database with."""
        return self.search_term.strip() or self.name


class VisionResult(BaseModel):
    items: list[VisionItem]
    #: Free-text caveats from the model ("sauce not visible", "partially eaten").
    notes: str = ""


class EstimatedNutrition(BaseModel):
    """Per-100 g nutrition the model produced from its own knowledge.

    **This is the one place in the codebase where a nutrition value is not
    measured, and it is deliberately quarantined.**

    It exists because a scan that identifies a food no database can match would
    otherwise be a dead end for the user. The rules that keep it honest:

    * it is only ever requested for foods USDA and the cache both failed to
      match, never as a shortcut;
    * it is stored under `FoodSource.AI_ESTIMATE`, excluded from food search, so
      it cannot reach anyone who did not watch it being estimated;
    * the app labels it on every screen it appears on.

    The optional nutrients stay optional. A model that does not know the fibre
    content should say so rather than produce a confident number, and `None`
    still renders as an em dash exactly like a USDA gap.
    """

    name: str = Field(min_length=1, max_length=120)
    kcal: float = Field(ge=0, le=900)
    protein_g: float = Field(ge=0, le=100)
    carbs_g: float = Field(ge=0, le=100)
    fat_g: float = Field(ge=0, le=100)
    fibre_g: float | None = Field(default=None, ge=0, le=100)
    sugars_g: float | None = Field(default=None, ge=0, le=100)


NUTRITION_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "foods": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "kcal": {"type": "NUMBER"},
                    "protein_g": {"type": "NUMBER"},
                    "carbs_g": {"type": "NUMBER"},
                    "fat_g": {"type": "NUMBER"},
                    "fibre_g": {"type": "NUMBER"},
                    "sugars_g": {"type": "NUMBER"},
                },
                "required": ["name", "kcal", "protein_g", "carbs_g", "fat_g"],
            },
        }
    },
    "required": ["foods"],
}

NUTRITION_PROMPT = """\
Give typical nutrition values PER 100 GRAMS for each food named below.

- Use well-established reference values for the plain, as-eaten form of the food.
- kcal, protein_g, carbs_g and fat_g are required. Omit fibre_g or sugars_g
  entirely if you are not reasonably confident — an omitted value is honest, a
  guessed one is not.
- Return one entry per food, with `name` copied exactly as given.
- Sanity-check yourself: protein_g + carbs_g + fat_g cannot exceed 100, and
  kcal should be close to 4*protein + 4*carbs + 9*fat.

Foods:
"""


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
                    "search_term": {"type": "STRING"},
                    "quantity_grams": {"type": "NUMBER"},
                    "confidence": {"type": "NUMBER"},
                },
                "required": ["name", "search_term", "quantity_grams", "confidence"],
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

- `name` is what the user sees, so describe the dish as served: "grilled
  chicken breast", "steamed broccoli". Never brand names, never dish poetry.
- `search_term` is the same food reduced to the plainest words a food database
  would file it under: drop cooking methods, adjectives and garnishes, keep the
  food itself. "grilled chicken breast" -> "chicken breast". "creamy mashed
  potatoes" -> "potato". "handful of cherry tomatoes" -> "tomato". Prefer one
  or two words. This is a lookup key, not a description.
- Estimate quantity_grams from visual cues (plate size, utensils, thickness).
  These are estimates the user will adjust; be realistic, not precise.
- confidence is 0 to 1: how sure you are of BOTH the identification and the
  portion. Sauces and hidden ingredients deserve low confidence.
- List at most 8 items. Merge duplicates. Ignore garnish under ~5 g.
- If the photo contains no food, return an empty items list and say why in
  notes.
- Do NOT estimate calories or nutrients. Only names and gram weights.
"""


def _model_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Pull the model's JSON out of the generateContent envelope."""
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        # Covers finishReason=SAFETY and =MAX_TOKENS, both of which return a
        # candidate with no parts. MAX_TOKENS here means thinking ate the whole
        # budget — see MAX_OUTPUT_TOKENS above.
        reason = (payload.get("candidates") or [{}])[0].get("finishReason", "unknown")
        raise VisionUnavailable(f"Gemini returned no content (finishReason={reason})") from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise VisionUnavailable("Gemini returned invalid JSON despite schema") from exc


def _parse_nutrition(payload: dict[str, Any]) -> dict[str, EstimatedNutrition]:
    """Validate estimated nutrition, dropping anything implausible.

    The bounds on `EstimatedNutrition` do real work here. A model that returns
    2400 kcal per 100 g has produced a number that would silently wreck a day's
    diary, and the right response is to drop the food back to "no match" — the
    user can still search for it manually — rather than store nonsense under a
    label that says "estimated" as though that made it usable.
    """
    raw = _model_json(payload)

    estimates: dict[str, EstimatedNutrition] = {}
    for entry in (raw.get("foods") or [])[:MAX_ITEMS]:
        try:
            estimate = EstimatedNutrition.model_validate(entry)
        except ValidationError:
            logger.warning("Dropping implausible nutrition estimate: %r", entry)
            continue
        estimates[estimate.name.strip().lower()] = estimate
    return estimates


def parse_vision_response(payload: dict[str, Any]) -> VisionResult:
    """Extract and validate the model's JSON from a generateContent response.

    Malformed items are dropped individually rather than failing the scan: one
    hallucinated 5 kg entry should not cost the user the four good ones.
    """
    raw = _model_json(payload)

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
            return await self._post_with_retry(
                client, url, body, settings.gemini_api_key, parse=parse_vision_response
            )
        finally:
            if self._client is None:
                await client.aclose()

    async def estimate_nutrition(self, names: list[str]) -> dict[str, EstimatedNutrition]:
        """Ask the model for per-100 g nutrition for foods no database matched.

        A second call rather than extra fields on the first, and that separation
        is the safeguard rather than an accident of design. The scan request has
        no nutrition field in its schema at all, so the identification step
        physically cannot return a calorie — which means this call is the only
        path by which an estimated number can enter the system, and it is
        reached only after USDA and the cache have both failed.

        Returns a mapping keyed by the name asked for. Missing keys are normal:
        anything the model declined or garbled is simply left unmatched, which
        the app already knows how to show.
        """
        settings = get_settings()
        if not settings.gemini_api_key:
            raise VisionNotConfigured("GEMINI_API_KEY is not set")
        if not names:
            return {}

        listing = "\n".join(f"- {name}" for name in names[:MAX_ITEMS])
        body = {
            "contents": [{"parts": [{"text": NUTRITION_PROMPT + listing}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": NUTRITION_SCHEMA,
                # Lower than the vision call. This is recall of reference values,
                # not interpretation of an image; variation is not a feature.
                "temperature": 0.0,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "thinkingConfig": {"thinkingBudget": THINKING_BUDGET_TOKENS},
            },
        }

        url = f"{BASE_URL}/models/{settings.gemini_model}:generateContent"
        client = self._client or httpx.AsyncClient(timeout=40.0)
        try:
            payload = await self._post_with_retry(
                client, url, body, settings.gemini_api_key, parse=_parse_nutrition
            )
        finally:
            if self._client is None:
                await client.aclose()

        return payload

    async def _post_with_retry[T](
        self,
        client: httpx.AsyncClient,
        url: str,
        body: dict[str, Any],
        api_key: str,
        *,
        parse: "Callable[[dict[str, Any]], T]",
    ) -> T:
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
                    # The shared free-tier budget is spent. Parse Google's own
                    # RetryInfo rather than guessing — see _quota_error.
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = {}
                    raise _quota_error(payload, response.text)

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
                    return parse(response.json())

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
