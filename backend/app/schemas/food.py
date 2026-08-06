"""Food and search schemas."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class PortionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    grams: float
    is_default: bool


class CustomFoodInput(BaseModel):
    """A food the user is entering from a label themselves.

    **This is the second place a number enters the app without a measurement
    behind it**, and unlike the AI estimate it is not a guess — it is a person
    copying the nutrition panel in front of them. That is a stronger claim than
    an inferred one, and a weaker one than USDA, so it is stored under its own
    source and labelled wherever it is shown.

    Every field is per 100 g, matching every other food in the database. Asking
    for "per serving" would mean converting on the way in, and a conversion the
    user cannot see is a conversion they cannot check.
    """

    name: str = Field(min_length=1, max_length=120)
    brand: str | None = Field(default=None, max_length=120)
    #: The barcode, when this is being created after a failed scan. Stored so a
    #: second scan of the same product finds the user's own entry rather than
    #: dead-ending again.
    barcode: str | None = Field(default=None, pattern=r"^\d{6,14}$")

    is_liquid: bool = False

    kcal: float = Field(ge=0, le=900)
    protein_g: float = Field(ge=0, le=100)
    carbs_g: float = Field(ge=0, le=100)
    fat_g: float = Field(ge=0, le=100)

    # Optional stay optional. A label that does not state fibre must produce a
    # null here, not a zero — the same rule every other source follows.
    sugars_g: float | None = Field(default=None, ge=0, le=100)
    saturated_fat_g: float | None = Field(default=None, ge=0, le=100)
    fibre_g: float | None = Field(default=None, ge=0, le=100)
    sodium_mg: float | None = Field(default=None, ge=0, le=100_000)

    #: The serving size on the pack, if there is one.
    serving_grams: float | None = Field(default=None, gt=0, le=1000)


class FoodRead(BaseModel):
    """A food, per 100 g or 100 ml.

    Note every optional nutrient is `float | None` rather than defaulting to 0.
    The distinction travels all the way to the screen: null renders as an em
    dash, meaning "this source did not report it", which is a different and
    honest claim from "there is none of it in this food".
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    source_id: str
    name: str
    brand: str | None
    is_liquid: bool

    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float

    sugars_g: float | None
    saturated_fat_g: float | None
    fibre_g: float | None
    sodium_mg: float | None

    #: Set when a report was upheld and the food was pulled from search.
    #:
    #: Sent rather than the row being hidden outright, because a withdrawn food
    #: is usually already in somebody's diary and that entry still has to render.
    #: What changes is that the screen says so — a past entry is a record of what
    #: was logged, not a number the app is still standing behind.
    withdrawn_reason: str | None = None

    portions: list[PortionRead] = Field(default_factory=list)


class FoodSearchResult(BaseModel):
    """Deliberately lighter than FoodRead.

    A search screen renders a list of rows; sending every nutrient and every
    portion for fifty results would be several times the payload for data the
    user cannot see until they tap one.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    name: str
    brand: str | None
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float


class QuickAddFood(FoodSearchResult):
    """A food the user logs often, with everything needed to re-log it.

    `last_quantity_grams` is the field that makes this worth having. A chip that
    only carries a food id still costs a trip through the portion screen; one
    that remembers the amount turns repeating breakfast into a single tap.
    """

    last_quantity_grams: float
    last_meal_slot: str
    #: Shown on the chip so the user can see *why* it is being offered, and so a
    #: one-off from last week is visibly different from a daily staple.
    times_logged: int


class FoodSearchResponse(BaseModel):
    query: str
    results: list[FoodSearchResult]
    #: True when results came only from our cache because USDA was unreachable.
    # The app says so rather than pretending the list is complete.
    upstream_unavailable: bool = False


class PopularFoodRead(BaseModel):
    """One entry in the curated browse list.

    Note what is absent: any nutrition value. This is a menu entry, not a food —
    the numbers arrive when `search_term` is resolved against USDA, which keeps
    the curated list from becoming a second, unmaintained source of truth.
    """

    name: str
    #: Stands in for a photograph. See services/popular_foods.py for why.
    emoji: str
    #: What to search USDA with. Not shown to the user.
    search_term: str
    category: str
