"""Triage for user-submitted foods.

**What the model is allowed to do here.** It reads a submission and says whether
it looks like a real food product and whether its numbers are self-consistent.
That is all. It cannot approve, reject, or change a single figure — those are the
admin's, and the separation is the whole design:

* the model's opinion lands in `llm_verdict` / `llm_reason`
* the decision lands in `review_status` / `reviewed_by`

Two columns, never one. Collapsing them would make it impossible to tell
afterwards whether a human ever looked, and would leave the door open for a later
change to promote the advice into an auto-approval — which is exactly the failure
this app refuses everywhere else.

**Why an LLM at all**, when `_atwater_check` already catches impossible macros:
arithmetic cannot tell that "Fresh Air, 0 kcal" is not a food, that a name is
abusive, or that 900 kcal per 100 g of "Lettuce" is wrong despite adding up. Those
are judgements about meaning, and they are what a reviewer would otherwise spend
their attention on.
"""

import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.core.tls import use_system_trust_store
from app.db.models.food import Food, LlmVerdict

logger = logging.getLogger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT_SECONDS = 30.0

PROMPT = """\
You are screening a food submitted to a nutrition database by a member of the
public. A human reviewer will make the final decision; your job is to sort the
queue and tell them what to look at.

Judge two things and nothing else:

1. Is this plausibly a real food or drink product?
2. Are its numbers consistent with what it claims to be?

Verdicts:
- "plausible"  — a real food, numbers reasonable for it.
- "suspect"    — probably real, but something is off: a figure that does not fit
                 the food, a name too vague to identify, a brand that reads
                 invented. Say which.
- "not_food"   — not a food or drink at all, gibberish, a joke entry, an advert,
                 or abusive text.

Rules:
- Judge the numbers against the food *named*. 900 kcal per 100 g is right for oil
  and wrong for lettuce, and only you can tell those apart.
- Do NOT propose corrected values. You are not the source of nutrition data here
  and a number you supply could end up in somebody's diary.
- A missing optional nutrient is not a fault. Blank means the label did not say.
- Be brief. `reason` is one sentence a reviewer reads at a glance.
"""

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["plausible", "suspect", "not_food"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
}


class ReviewOpinion(BaseModel):
    verdict: LlmVerdict
    reason: str = Field(default="", max_length=500)


def describe(food: Food) -> str:
    """The submission as the model sees it.

    Only the fields relevant to the judgement. The author's identity is
    deliberately absent: who submitted it must not influence whether it looks
    like a food.
    """
    lines = [
        f"Name: {food.name}",
        f"Brand: {food.brand or '(none given)'}",
        f"Per 100 {'ml' if food.is_liquid else 'g'}:",
        f"  calories: {food.kcal} kcal",
        f"  protein: {food.protein_g} g",
        f"  carbohydrate: {food.carbs_g} g",
        f"  fat: {food.fat_g} g",
    ]
    for label, value in (
        ("sugars", food.sugars_g),
        ("saturated fat", food.saturated_fat_g),
        ("fibre", food.fibre_g),
        ("sodium", food.sodium_mg),
    ):
        lines.append(f"  {label}: {'not stated' if value is None else value}")
    return "\n".join(lines)


class FoodReviewer:
    """Asks Gemini for an opinion on a submission."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def assess(self, food: Food) -> ReviewOpinion | None:
        """Return the model's opinion, or None if it could not be obtained.

        None rather than an exception: triage is an aid, and a submission whose
        screening failed should still reach a human. Blocking the queue on a
        third-party outage would make the feature less reliable than having no
        triage at all.
        """
        settings = get_settings()
        key = settings.gemini_key_for_text
        if not key:
            logger.info("No Gemini key configured; submission goes to review unscreened")
            return None

        use_system_trust_store()

        body = {
            "contents": [{"parts": [{"text": f"{PROMPT}\n\n{describe(food)}"}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": RESPONSE_SCHEMA,
                "temperature": 0.1,
                "max_output_tokens": 512,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }

        client = self._client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
        try:
            response = await client.post(
                f"{BASE_URL}/models/{settings.gemini_model}:generateContent",
                json=body,
                headers={"x-goog-api-key": key},
            )
            if not response.is_success:
                logger.warning("Review screening failed: %s", response.status_code)
                return None

            payload = response.json()
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            return ReviewOpinion.model_validate(json.loads(text))
        except (httpx.HTTPError, KeyError, IndexError, ValueError, ValidationError) as exc:
            # Every failure is the same outcome — unscreened, still reviewed.
            logger.warning("Could not screen submission %s: %s", food.id, exc)
            return None
        finally:
            if self._client is None:
                await client.aclose()
