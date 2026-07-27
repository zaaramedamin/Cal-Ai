"""Daily calorie and macronutrient targets.

The single source of truth for every number this app tells a user to eat. Pure
functions only — no database, no I/O, no clock — so every branch, clamp and
boundary can be tested directly.

Two properties are deliberate:

**It explains itself.** Alongside the numbers, `calculate_targets` returns an
ordered derivation. Users trust a number they can follow, and "2,140 kcal"
with no reasoning is indistinguishable from a guess. The results screen renders
this list directly rather than re-describing the maths in the UI layer, where it
would drift out of step with the code.

**It refuses bad input.** Body stats outside sane human ranges raise rather than
silently producing a number, because a typo (17 cm instead of 170) would
otherwise yield a confident and dangerous target.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

KCAL_PER_GRAM_PROTEIN: Final = 4
KCAL_PER_GRAM_CARBS: Final = 4
KCAL_PER_GRAM_FAT: Final = 9

#: Energy in a kilogram of body fat. The usual 3,500 kcal-per-pound figure,
#: converted. An approximation — real bodies are not this tidy — used only to
#: warn about an over-aggressive rate of loss, never to promise a result.
KCAL_PER_KG_BODY_FAT: Final = 7700

MIN_AGE_YEARS: Final = 13
MAX_AGE_YEARS: Final = 100
MIN_HEIGHT_CM: Final = 100.0
MAX_HEIGHT_CM: Final = 250.0
MIN_WEIGHT_KG: Final = 30.0
MAX_WEIGHT_KG: Final = 300.0

#: Absolute floors. Below these, a target stops being a diet and becomes a
#: medical matter that an app has no business prescribing.
MIN_CALORIES_MALE: Final = 1500
MIN_CALORIES_FEMALE: Final = 1200

#: Weekly weight change beyond this fraction of bodyweight is worth warning
#: about — faster loss increasingly comes from muscle rather than fat.
MAX_SAFE_WEEKLY_CHANGE_FRACTION: Final = 0.01


class Sex(StrEnum):
    """Biological sex, used only for the Mifflin-St Jeor constant and the floor.

    Named `sex` rather than `gender` on purpose: the equation is calibrated on
    body composition, not identity, and conflating the two makes the field
    impossible to explain honestly to a user.
    """

    MALE = "male"
    FEMALE = "female"


class ActivityLevel(StrEnum):
    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"


class Goal(StrEnum):
    CUT = "cut"
    MAINTAIN = "maintain"
    LEAN_BULK = "lean_bulk"
    BULK = "bulk"


ACTIVITY_MULTIPLIERS: Final[dict[ActivityLevel, float]] = {
    ActivityLevel.SEDENTARY: 1.200,
    ActivityLevel.LIGHT: 1.375,
    ActivityLevel.MODERATE: 1.550,
    ActivityLevel.ACTIVE: 1.725,
    ActivityLevel.VERY_ACTIVE: 1.900,
}

GOAL_MULTIPLIERS: Final[dict[Goal, float]] = {
    Goal.CUT: 0.80,
    Goal.MAINTAIN: 1.00,
    Goal.LEAN_BULK: 1.10,
    Goal.BULK: 1.15,
}

#: Grams of protein per kg of bodyweight. Higher on a cut: in a calorie deficit
#: protein is what preserves muscle, so the requirement goes up exactly when
#: total intake goes down.
PROTEIN_PER_KG: Final[dict[Goal, float]] = {
    Goal.CUT: 2.2,
    Goal.MAINTAIN: 1.8,
    Goal.LEAN_BULK: 1.8,
    Goal.BULK: 1.8,
}

FAT_PER_KG: Final = 0.9

#: Fat below roughly a fifth of intake starts to interfere with hormone
#: production and the absorption of fat-soluble vitamins.
MIN_FAT_FRACTION_OF_CALORIES: Final = 0.20


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class InvalidBodyStats(ValueError):
    """Input outside the range this calculator will produce a number for."""


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class DerivationStep:
    """One line of the explanation shown to the user."""

    label: str
    value: str
    detail: str


@dataclass(frozen=True, slots=True)
class MacroTargets:
    protein_g: int
    carbs_g: int
    fat_g: int

    @property
    def calories(self) -> int:
        """Energy the macros actually add up to.

        Rounding each macro to a whole gram means this can differ from the
        calorie target by a couple of kcal. Exposing it rather than hiding it
        keeps the two numbers reconcilable instead of mysteriously disagreeing.
        """
        return (
            self.protein_g * KCAL_PER_GRAM_PROTEIN
            + self.carbs_g * KCAL_PER_GRAM_CARBS
            + self.fat_g * KCAL_PER_GRAM_FAT
        )


@dataclass(frozen=True, slots=True)
class NutritionTargets:
    bmr: int
    tdee: int
    #: Before any safety clamp — kept so the explanation can be honest about a
    #: target having been raised, rather than silently showing a different number
    #: from the one the goal implies.
    uncapped_calories: int
    calories: int
    macros: MacroTargets
    was_clamped: bool
    warnings: list[str] = field(default_factory=list)
    derivation: list[DerivationStep] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def validate_body_stats(*, age_years: int, height_cm: float, weight_kg: float) -> None:
    """Reject input a human body cannot have.

    Validated here as well as at the API boundary, because this module is the
    thing that must never emit a nonsense number — and a later caller (a script,
    a test, Phase 6's recalculation) might not go through the API at all.
    """
    if not MIN_AGE_YEARS <= age_years <= MAX_AGE_YEARS:
        raise InvalidBodyStats(
            f"Age must be between {MIN_AGE_YEARS} and {MAX_AGE_YEARS} years, got {age_years}."
        )
    if not MIN_HEIGHT_CM <= height_cm <= MAX_HEIGHT_CM:
        raise InvalidBodyStats(
            f"Height must be between {MIN_HEIGHT_CM:.0f} and {MAX_HEIGHT_CM:.0f} cm, "
            f"got {height_cm}."
        )
    if not MIN_WEIGHT_KG <= weight_kg <= MAX_WEIGHT_KG:
        raise InvalidBodyStats(
            f"Weight must be between {MIN_WEIGHT_KG:.0f} and {MAX_WEIGHT_KG:.0f} kg, "
            f"got {weight_kg}."
        )


# --------------------------------------------------------------------------- #
# The calculation
# --------------------------------------------------------------------------- #


def calculate_bmr(*, sex: Sex, age_years: int, height_cm: float, weight_kg: float) -> float:
    """Basal metabolic rate — Mifflin-St Jeor.

    Energy the body uses at complete rest. Mifflin-St Jeor rather than the older
    Harris-Benedict because it is measurably more accurate for modern
    populations; both are estimates from population averages, which is why the
    clamps below matter.

        Male:   (10 x kg) + (6.25 x cm) - (5 x age) + 5
        Female: (10 x kg) + (6.25 x cm) - (5 x age) - 161
    """
    base = (10 * weight_kg) + (6.25 * height_cm) - (5 * age_years)
    return base + 5 if sex is Sex.MALE else base - 161


def calculate_tdee(bmr: float, activity_level: ActivityLevel) -> float:
    """Total daily energy expenditure: BMR scaled for how much you move."""
    return bmr * ACTIVITY_MULTIPLIERS[activity_level]


def calculate_macros(*, calories: int, weight_kg: float, goal: Goal) -> MacroTargets:
    """Split a calorie target into protein, fat and carbohydrate.

    Order matters. Protein and fat are set from bodyweight because that is what
    the body's requirement actually scales with; carbohydrate takes whatever
    energy is left. Setting carbs first would let protein fall wherever the
    remainder happened to land.
    """
    protein_g = round(PROTEIN_PER_KG[goal] * weight_kg)

    fat_from_weight = FAT_PER_KG * weight_kg
    fat_floor = (MIN_FAT_FRACTION_OF_CALORIES * calories) / KCAL_PER_GRAM_FAT
    fat_g = round(max(fat_from_weight, fat_floor))

    remaining = calories - (protein_g * KCAL_PER_GRAM_PROTEIN) - (fat_g * KCAL_PER_GRAM_FAT)

    # Reachable, and it must not produce a negative number. A heavy person on an
    # aggressive cut whose target was clamped up to BMR can need more energy for
    # protein and fat alone than the target allows. Carbs floor at zero and the
    # caller warns; silently emitting -18 g would be worse than an awkward truth.
    carbs_g = max(0, round(remaining / KCAL_PER_GRAM_CARBS))

    return MacroTargets(protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g)


def calculate_targets(
    *,
    sex: Sex,
    age_years: int,
    height_cm: float,
    weight_kg: float,
    activity_level: ActivityLevel,
    goal: Goal,
) -> NutritionTargets:
    """Produce a full daily target, with its derivation and any warnings."""
    validate_body_stats(age_years=age_years, height_cm=height_cm, weight_kg=weight_kg)

    bmr = calculate_bmr(sex=sex, age_years=age_years, height_cm=height_cm, weight_kg=weight_kg)
    tdee = calculate_tdee(bmr, activity_level)
    goal_calories = tdee * GOAL_MULTIPLIERS[goal]

    # ---- safety floors ---------------------------------------------------
    absolute_floor = MIN_CALORIES_MALE if sex is Sex.MALE else MIN_CALORIES_FEMALE
    floor = max(bmr, absolute_floor)
    calories = round(max(goal_calories, floor))
    was_clamped = calories > round(goal_calories)

    warnings: list[str] = []
    if was_clamped:
        reason = (
            "your basal metabolic rate"
            if bmr >= absolute_floor
            else f"the {absolute_floor} kcal minimum"
        )
        warnings.append(
            f"Your target was raised to {calories} kcal to stay at or above {reason}. "
            f"Eating below that reliably costs muscle and energy rather than fat."
        )

    macros = calculate_macros(calories=calories, weight_kg=weight_kg, goal=goal)

    if macros.carbs_g == 0:
        warnings.append(
            "Protein and fat alone account for your whole calorie target, leaving no room for "
            "carbohydrate. Consider a less aggressive goal, or treat these macros as a ceiling."
        )

    # ---- rate-of-change warning ------------------------------------------
    daily_delta = calories - tdee
    weekly_kg_change = abs(daily_delta) * 7 / KCAL_PER_KG_BODY_FAT
    max_safe_weekly = weight_kg * MAX_SAFE_WEEKLY_CHANGE_FRACTION
    if weekly_kg_change > max_safe_weekly:
        direction = "loss" if daily_delta < 0 else "gain"
        warnings.append(
            f"This pace implies about {weekly_kg_change:.1f} kg of {direction} per week, "
            f"more than 1% of your bodyweight ({max_safe_weekly:.1f} kg). "
            f"Faster is not better — beyond this, more of the change comes from muscle."
        )

    return NutritionTargets(
        bmr=round(bmr),
        tdee=round(tdee),
        uncapped_calories=round(goal_calories),
        calories=calories,
        macros=macros,
        was_clamped=was_clamped,
        warnings=warnings,
        derivation=_build_derivation(
            sex=sex,
            age_years=age_years,
            height_cm=height_cm,
            weight_kg=weight_kg,
            activity_level=activity_level,
            goal=goal,
            bmr=bmr,
            tdee=tdee,
            goal_calories=goal_calories,
            calories=calories,
            was_clamped=was_clamped,
            macros=macros,
        ),
    )


def _build_derivation(
    *,
    sex: Sex,
    age_years: int,
    height_cm: float,
    weight_kg: float,
    activity_level: ActivityLevel,
    goal: Goal,
    bmr: float,
    tdee: float,
    goal_calories: float,
    calories: int,
    was_clamped: bool,
    macros: MacroTargets,
) -> list[DerivationStep]:
    """The explanation the results screen renders.

    Built here, next to the maths, so it cannot describe a calculation the code
    no longer performs.
    """
    constant = "+ 5" if sex is Sex.MALE else "- 161"
    steps = [
        DerivationStep(
            label="Basal metabolic rate",
            value=f"{round(bmr):,} kcal",
            detail=(
                f"Mifflin-St Jeor: (10 x {weight_kg:g} kg) + (6.25 x {height_cm:g} cm) "
                f"- (5 x {age_years}) {constant}. This is what your body uses at rest."
            ),
        ),
        DerivationStep(
            label="Daily expenditure",
            value=f"{round(tdee):,} kcal",
            detail=(
                f"BMR x {ACTIVITY_MULTIPLIERS[activity_level]:.3f} for "
                f"{activity_level.value.replace('_', ' ')} activity."
            ),
        ),
        DerivationStep(
            label=f"Adjusted to {goal.value.replace('_', ' ')}",
            value=f"{round(goal_calories):,} kcal",
            detail=f"Daily expenditure x {GOAL_MULTIPLIERS[goal]:.2f}.",
        ),
    ]

    if was_clamped:
        steps.append(
            DerivationStep(
                label="Raised to a safe minimum",
                value=f"{calories:,} kcal",
                detail=(
                    "Your goal implied a lower number than is safe to sustain, so it was "
                    "raised. See the note below."
                ),
            )
        )

    steps.append(
        DerivationStep(
            label="Protein",
            value=f"{macros.protein_g} g",
            detail=(
                f"{PROTEIN_PER_KG[goal]:g} g per kg of bodyweight. Set first, because in a "
                "deficit protein is what protects muscle."
            ),
        )
    )
    steps.append(
        DerivationStep(
            label="Fat",
            value=f"{macros.fat_g} g",
            detail=(
                f"{FAT_PER_KG:g} g per kg, with a floor of "
                f"{MIN_FAT_FRACTION_OF_CALORIES:.0%} of calories for hormone health."
            ),
        )
    )
    steps.append(
        DerivationStep(
            label="Carbohydrate",
            value=f"{macros.carbs_g} g",
            detail="Whatever energy is left after protein and fat, divided by 4 kcal per gram.",
        )
    )

    return steps
