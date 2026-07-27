"""Recipe nutrition.

Pure functions over already-loaded ingredients — no database access — so the
arithmetic can be tested exhaustively without a fixture, and so the same code
serves both "show me the totals as I build this" and "snapshot this into the
diary".
"""

from dataclasses import dataclass, field

#: Nutrients a source may legitimately not report. Kept identical to the diary's
#: list; both describe the same honesty rule.
OPTIONAL_NUTRIENTS = ("sugars_g", "saturated_fat_g", "fibre_g", "sodium_mg")

REQUIRED_NUTRIENTS = ("kcal", "protein_g", "carbs_g", "fat_g")


@dataclass(frozen=True, slots=True)
class IngredientNutrition:
    """One ingredient's per-100 g values, and how much of it is used."""

    grams: float
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    sugars_g: float | None = None
    saturated_fat_g: float | None = None
    fibre_g: float | None = None
    sodium_mg: float | None = None


@dataclass(frozen=True, slots=True)
class RecipeNutrition:
    """Totals for the whole recipe and for one serving."""

    total_grams: float
    total: dict[str, float | None]
    per_serving: dict[str, float | None]
    #: Nutrients at least one ingredient did not report, so the total is a floor
    #: rather than a complete figure.
    partial: list[str] = field(default_factory=list)


def calculate_recipe_nutrition(
    ingredients: list[IngredientNutrition], servings: int
) -> RecipeNutrition:
    """Sum ingredients and divide by servings.

    Two rules carried over from everywhere else in this codebase, because a
    recipe is exactly where they would be easiest to quietly break:

    * A missing nutrient stays missing. `None` never becomes `0` by passing
      through a sum — if one ingredient does not report fibre, the recipe's fibre
      total is a minimum, and says so.
    * Nothing is rounded until the end. Rounding each ingredient and then summing
      accumulates error with every item; a twelve-ingredient recipe would drift
      noticeably from the sum of what the user was shown.
    """
    if servings < 1:
        raise ValueError("A recipe must have at least one serving.")

    total_grams = round(sum(item.grams for item in ingredients), 2)

    total: dict[str, float | None] = {}
    partial: list[str] = []

    for nutrient in REQUIRED_NUTRIENTS:
        total[nutrient] = round(
            sum(getattr(item, nutrient) * item.grams / 100.0 for item in ingredients), 2
        )

    for nutrient in OPTIONAL_NUTRIENTS:
        contributions = [
            getattr(item, nutrient) * item.grams / 100.0
            for item in ingredients
            if getattr(item, nutrient) is not None
        ]
        total[nutrient] = round(sum(contributions), 2) if contributions else None

        if ingredients and len(contributions) < len(ingredients):
            partial.append(nutrient)

    per_serving = {
        nutrient: (None if value is None else round(value / servings, 2))
        for nutrient, value in total.items()
    }

    return RecipeNutrition(
        total_grams=total_grams,
        total=total,
        per_serving=per_serving,
        partial=partial,
    )
