"""Diary schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.diary import MealSlot
from app.schemas.profile import MacroTargetsRead


class DiaryEntryCreate(BaseModel):
    food_id: uuid.UUID
    meal_slot: MealSlot
    quantity_grams: float = Field(gt=0, le=10_000)
    #: Which local day to file it under. Optional — the server uses the user's
    #: local today when absent. Supplied only for back-filling a past day.
    local_date: date | None = None


class DiaryEntryUpdate(BaseModel):
    quantity_grams: float | None = Field(default=None, gt=0, le=10_000)
    meal_slot: MealSlot | None = None


class DiaryEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    local_date: date
    meal_slot: MealSlot
    food_id: uuid.UUID | None
    recipe_id: uuid.UUID | None
    food_name: str
    food_brand: str | None
    quantity_grams: float
    #: Set only for recipe entries. The app shows "1.5 servings" rather than the
    #: gram weight, because that is how someone thinks about a portion they
    #: served themselves.
    servings: float | None

    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    sugars_g: float | None
    saturated_fat_g: float | None
    fibre_g: float | None
    sodium_mg: float | None

    logged_at: datetime


class NutrientTotals(BaseModel):
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float

    #: Null when *no* entry reported the nutrient; otherwise the sum of those
    #: that did. Paired with the `partial` flags below so a total is never
    #: presented as complete when it is not.
    sugars_g: float | None
    saturated_fat_g: float | None
    fibre_g: float | None
    sodium_mg: float | None

    #: Names of nutrients where at least one entry had no data. The app shows
    #: "at least 12 g" rather than "12 g", because summing over holes and
    #: presenting the result as a total is exactly the kind of invented number
    #: this project refuses to produce.
    partial: list[str] = Field(default_factory=list)


class MealGroup(BaseModel):
    meal_slot: MealSlot
    entries: list[DiaryEntryRead]
    totals: NutrientTotals


class DaySummary(BaseModel):
    local_date: date
    meals: list[MealGroup]
    totals: NutrientTotals
    target_calories: int
    target_macros: MacroTargetsRead
    remaining_calories: int
