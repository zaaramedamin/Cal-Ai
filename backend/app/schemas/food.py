"""Food and search schemas."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class PortionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    grams: float
    is_default: bool


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


class FoodSearchResponse(BaseModel):
    query: str
    results: list[FoodSearchResult]
    #: True when results came only from our cache because USDA was unreachable.
    # The app says so rather than pretending the list is complete.
    upstream_unavailable: bool = False
