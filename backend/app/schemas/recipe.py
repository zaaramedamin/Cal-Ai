"""Recipe schemas."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

MAX_INGREDIENTS = 50


class IngredientInput(BaseModel):
    food_id: uuid.UUID
    grams: float = Field(gt=0, le=10_000)


class RecipeInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    servings: int = Field(ge=1, le=100)
    # A cap, so one request cannot ask the server to load an unbounded number of
    # foods. Fifty is far beyond any real recipe.
    ingredients: list[IngredientInput] = Field(min_length=1, max_length=MAX_INGREDIENTS)


class IngredientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    food_id: uuid.UUID
    food_name: str
    food_brand: str | None
    grams: float
    #: This ingredient's contribution at the quantity used.
    kcal: float

    # Per 100 g, so the builder can recompute totals live while the user edits
    # quantities. Without these the edit screen would have to fetch every food
    # separately — one request per ingredient — or show wrong macros.
    kcal_per_100g: float
    protein_g_per_100g: float
    carbs_g_per_100g: float
    fat_g_per_100g: float


class RecipeNutritionRead(BaseModel):
    total_grams: float
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    sugars_g: float | None
    saturated_fat_g: float | None
    fibre_g: float | None
    sodium_mg: float | None
    partial: list[str]


class RecipeRead(BaseModel):
    id: uuid.UUID
    name: str
    servings: int
    ingredients: list[IngredientRead]
    #: For the whole recipe.
    total: RecipeNutritionRead
    #: For one serving — the number the user actually logs against.
    per_serving: RecipeNutritionRead


class RecipeSummary(BaseModel):
    """Row shape for the recipe list. Lighter than the full read."""

    id: uuid.UUID
    name: str
    servings: int
    ingredient_count: int
    kcal_per_serving: float
    protein_g_per_serving: float
    carbs_g_per_serving: float
    fat_g_per_serving: float


class LogRecipeInput(BaseModel):
    servings: float = Field(gt=0, le=20)
