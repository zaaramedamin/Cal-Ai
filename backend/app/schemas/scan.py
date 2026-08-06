"""Meal photo scan schemas.

Read `ScannedItem` closely: the AI's contribution is `detected_name` and
`estimated_grams`, and the nutrition lives entirely inside `match`, which is a
row from our USDA-backed cache. Nothing in this response carries a calorie the
model made up, because the model is never asked for one.
"""

from pydantic import BaseModel, Field, field_validator

from app.schemas.food import FoodSearchResult

#: Roughly 8 MB of image once decoded. Base64 inflates by 4/3, so the encoded
#: string is bounded here. The app sends ~200 KB after resizing; this exists to
#: stop somebody posting a 50 MB raw capture, not to constrain normal use.
MAX_IMAGE_BASE64_CHARS = 11_000_000

ALLOWED_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


class DescribeRequest(BaseModel):
    """A meal written in words rather than photographed.

    Bounded at 500 characters: a meal description is a sentence or two, and the
    limit is what stops the endpoint being used as a general-purpose prompt into
    a shared Gemini budget.
    """

    description: str = Field(min_length=3, max_length=500)


class ScanRequest(BaseModel):
    #: Base64 without a data-URL prefix. The app strips it before sending.
    image_base64: str = Field(min_length=64, max_length=MAX_IMAGE_BASE64_CHARS)
    media_type: str = "image/jpeg"

    @field_validator("media_type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in ALLOWED_MEDIA_TYPES:
            raise ValueError(f"media_type must be one of {sorted(ALLOWED_MEDIA_TYPES)}")
        return value


class ScannedItem(BaseModel):
    """One food the model saw, paired with our best database match."""

    #: What the model called it, kept verbatim so the user can see what was
    #: recognised even when we could not match it.
    detected_name: str
    #: The model's visual estimate. Editable in the app before anything is logged.
    estimated_grams: float
    confidence: float
    #: None when nothing matched and no estimate could be produced. The app
    #: offers a manual search rather than showing numbers for it.
    #:
    #: When `match.source` is `ai_estimate` the numbers came from the model's own
    #: knowledge rather than a measurement, and the app must label them. That is
    #: why `source` is on `FoodSearchResult` — it is not decoration, it is how a
    #: client tells a measured number from an estimated one.
    match: FoodSearchResult | None = None


class ScanResponse(BaseModel):
    items: list[ScannedItem]
    #: The model's own caveats ("sauce not visible", "no food in this photo").
    notes: str = ""
    #: How many detected items have no numbers at all. Surfaced so the app can
    #: say "2 items need a manual search" instead of quietly dropping them.
    unmatched_count: int = 0
    #: How many are AI estimates rather than database entries. Lets the app warn
    #: once at the top instead of relying on the user reading every badge.
    estimated_count: int = 0
