"""Meals a user composes from catalogue ingredients.

**How this differs from a recipe, which already exists.**

A recipe divides into servings — you cook a chilli for four and log one portion.
A meal does not: it is the plate you personally assembled, logged whole. "Two
eggs, 60 g of oats, a banana" is not a dish anyone serves in portions, it is
Tuesday breakfast, and asking the user how many servings their own breakfast
makes is a question with no meaning.

The other difference is what they are built from. Recipes are assembled out of
raw USDA search results; meals are assembled out of the curated catalogue, which
is the whole reason this exists — picking "2 eggs" from a menu is a thing a
person can do, and picking *Egg, whole, raw, fresh* out of forty search results
is not.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.catalogue import UnitKind

#: Enough for a genuinely elaborate plate, low enough that a runaway client
#: cannot make one document expensive to read.
MAX_MEAL_ITEMS = 30


class MealItemInput(BaseModel):
    """One ingredient, in the food's own unit."""

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    amount: float = Field(gt=0, le=10_000)


class MealInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    items: list[MealItemInput] = Field(min_length=1, max_length=MAX_MEAL_ITEMS)

    @field_validator("name")
    @classmethod
    def _tidy_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A meal needs a name.")
        return cleaned

    @field_validator("items")
    @classmethod
    def _no_duplicate_slugs(cls, items: list[MealItemInput]) -> list[MealItemInput]:
        """Reject the same food twice.

        Not a technical constraint — it would sum correctly either way. It is a
        usability one: two "Egg" rows in a meal is always a mis-tap or a
        double-submit, and the user meant to change the amount on the row they
        already had.
        """
        slugs = [item.slug for item in items]
        if len(set(slugs)) != len(slugs):
            raise ValueError("An ingredient appears twice. Change its amount instead.")
        return items


class MealItemRead(BaseModel):
    """An ingredient resolved against the catalogue."""

    slug: str
    name_en: str
    name_fr: str
    emoji: str
    photo: str | None
    unit: UnitKind
    amount: float
    grams: float
    #: This ingredient's contribution to the meal, already scaled.
    kcal: float


class MealTotals(BaseModel):
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    sugars_g: float | None
    saturated_fat_g: float | None
    fibre_g: float | None
    sodium_mg: float | None
    total_grams: float
    #: Nutrients at least one ingredient does not report, so the figure is a
    #: floor rather than a total. Carried all the way to the screen.
    partial: list[str] = Field(default_factory=list)


class MealRead(BaseModel):
    id: str
    name: str
    items: list[MealItemRead]
    totals: MealTotals
    created_at: datetime
    #: Ingredients that were in the meal but are no longer in the catalogue.
    #:
    #: Mongo has no foreign keys, so this is the case Postgres used to prevent
    #: outright. Reporting the slugs is better than either silently dropping them
    #: (the meal's calories would quietly fall) or failing the whole read (one
    #: retired ingredient would make the meal unopenable).
    missing_slugs: list[str] = Field(default_factory=list)
