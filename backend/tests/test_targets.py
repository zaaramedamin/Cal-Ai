"""Calorie and macro target calculations.

Full coverage of the module the brief singles out, including every clamp and
every validation boundary. Expected values are worked out by hand in the
docstrings rather than computed by re-implementing the formula, because a test
that recomputes the thing it is testing proves only that the code is
self-consistent.
"""

import pytest

from app.nutrition.targets import (
    ACTIVITY_MULTIPLIERS,
    DEFAULT_WEEKLY_RATE_KG,
    GOAL_MULTIPLIERS,
    KCAL_PER_GRAM_CARBS,
    KCAL_PER_GRAM_FAT,
    KCAL_PER_GRAM_PROTEIN,
    MAX_AGE_YEARS,
    MAX_HEIGHT_CM,
    MAX_WEEKLY_RATE_KG,
    MAX_WEIGHT_KG,
    MIN_AGE_YEARS,
    MIN_CALORIES_FEMALE,
    MIN_CALORIES_MALE,
    MIN_HEIGHT_CM,
    MIN_WEIGHT_KG,
    ActivityLevel,
    Goal,
    InvalidBodyStats,
    Sex,
    calculate_bmr,
    calculate_macros,
    calculate_targets,
    calculate_tdee,
    validate_body_stats,
)

# A healthy reference person used across several tests.
REFERENCE = {
    "sex": Sex.MALE,
    "age_years": 30,
    "height_cm": 180.0,
    "weight_kg": 80.0,
    "activity_level": ActivityLevel.MODERATE,
    "goal": Goal.MAINTAIN,
}


# --------------------------------------------------------------------------- #
# BMR — Mifflin-St Jeor
# --------------------------------------------------------------------------- #


def test_bmr_male() -> None:
    """(10 x 80) + (6.25 x 180) - (5 x 30) + 5 = 800 + 1125 - 150 + 5 = 1780"""
    assert calculate_bmr(sex=Sex.MALE, age_years=30, height_cm=180, weight_kg=80) == 1780.0


def test_bmr_female() -> None:
    """(10 x 60) + (6.25 x 165) - (5 x 25) - 161 = 600 + 1031.25 - 125 - 161 = 1345.25"""
    assert calculate_bmr(sex=Sex.FEMALE, age_years=25, height_cm=165, weight_kg=60) == 1345.25


def test_male_and_female_differ_by_exactly_166() -> None:
    """The only difference in the equation is +5 versus -161."""
    common = {"age_years": 30, "height_cm": 175.0, "weight_kg": 70.0}
    male = calculate_bmr(sex=Sex.MALE, **common)
    female = calculate_bmr(sex=Sex.FEMALE, **common)
    assert male - female == 166.0


def test_bmr_falls_with_age() -> None:
    common = {"sex": Sex.MALE, "height_cm": 180.0, "weight_kg": 80.0}
    assert calculate_bmr(age_years=50, **common) < calculate_bmr(age_years=30, **common)


# --------------------------------------------------------------------------- #
# TDEE
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("level", "multiplier"),
    [
        (ActivityLevel.SEDENTARY, 1.200),
        (ActivityLevel.LIGHT, 1.375),
        (ActivityLevel.MODERATE, 1.550),
        (ActivityLevel.ACTIVE, 1.725),
        (ActivityLevel.VERY_ACTIVE, 1.900),
    ],
)
def test_activity_multipliers_match_the_specification(
    level: ActivityLevel, multiplier: float
) -> None:
    assert ACTIVITY_MULTIPLIERS[level] == multiplier
    assert calculate_tdee(2000.0, level) == pytest.approx(2000.0 * multiplier)


def test_every_activity_level_has_a_multiplier() -> None:
    """A new enum member without a multiplier would KeyError at runtime."""
    assert set(ACTIVITY_MULTIPLIERS) == set(ActivityLevel)


# --------------------------------------------------------------------------- #
# Goals
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("goal", "multiplier"),
    [(Goal.CUT, 0.80), (Goal.MAINTAIN, 1.00), (Goal.LEAN_BULK, 1.10), (Goal.BULK, 1.15)],
)
def test_goal_multipliers_match_the_specification(goal: Goal, multiplier: float) -> None:
    assert GOAL_MULTIPLIERS[goal] == multiplier


def test_every_goal_has_a_multiplier_and_a_protein_target() -> None:
    from app.nutrition.targets import PROTEIN_PER_KG

    assert set(GOAL_MULTIPLIERS) == set(Goal)
    assert set(PROTEIN_PER_KG) == set(Goal)


def test_maintain_equals_tdee() -> None:
    result = calculate_targets(**REFERENCE)
    assert result.calories == result.tdee


def test_goals_are_ordered_by_calories() -> None:
    def calories_for(goal: Goal) -> int:
        return calculate_targets(**{**REFERENCE, "goal": goal}).calories

    assert (
        calories_for(Goal.CUT)
        < calories_for(Goal.MAINTAIN)
        < calories_for(Goal.LEAN_BULK)
        < calories_for(Goal.BULK)
    )


def test_reference_person_maintenance_target() -> None:
    """BMR 1780, x1.550 = 2759 kcal, maintain leaves it unchanged."""
    result = calculate_targets(**REFERENCE)
    assert result.bmr == 1780
    assert result.tdee == 2759
    assert result.calories == 2759
    assert not result.was_clamped


# --------------------------------------------------------------------------- #
# Safety clamps
# --------------------------------------------------------------------------- #


def test_target_is_never_below_bmr() -> None:
    """Female, 25, 165 cm, 60 kg, sedentary, cut.

    BMR 1345.25, TDEE 1614.3, cut implies 1291.44 — below BMR, so it is raised
    to 1345. Above the 1200 absolute floor, so BMR is the binding constraint.
    """
    result = calculate_targets(
        sex=Sex.FEMALE,
        age_years=25,
        height_cm=165,
        weight_kg=60,
        activity_level=ActivityLevel.SEDENTARY,
        goal=Goal.CUT,
    )
    assert result.uncapped_calories == 1291
    assert result.calories == 1345
    assert result.calories >= result.bmr
    assert result.was_clamped


def test_female_absolute_floor_applies_when_bmr_is_lower() -> None:
    """Female, 70, 150 cm, 40 kg, sedentary, cut.

    BMR 826.5 — below the 1200 floor — so the floor binds, not BMR.
    """
    result = calculate_targets(
        sex=Sex.FEMALE,
        age_years=70,
        height_cm=150,
        weight_kg=40,
        activity_level=ActivityLevel.SEDENTARY,
        goal=Goal.CUT,
    )
    assert result.bmr < MIN_CALORIES_FEMALE
    assert result.calories == MIN_CALORIES_FEMALE
    assert result.was_clamped


def test_male_absolute_floor_is_1500() -> None:
    """Male, 80, 155 cm, 45 kg, sedentary, cut.

    BMR = 450 + 968.75 - 400 + 5 = 1023.75, below the 1500 floor.
    """
    result = calculate_targets(
        sex=Sex.MALE,
        age_years=80,
        height_cm=155,
        weight_kg=45,
        activity_level=ActivityLevel.SEDENTARY,
        goal=Goal.CUT,
    )
    assert result.bmr < MIN_CALORIES_MALE
    assert result.calories == MIN_CALORIES_MALE


def test_clamping_explains_itself() -> None:
    """A raised number with no explanation looks like a bug to the user."""
    result = calculate_targets(
        sex=Sex.FEMALE,
        age_years=70,
        height_cm=150,
        weight_kg=40,
        activity_level=ActivityLevel.SEDENTARY,
        goal=Goal.CUT,
    )
    assert result.warnings
    assert any("raised" in warning.lower() for warning in result.warnings)


def test_no_clamp_means_no_clamp_warning() -> None:
    result = calculate_targets(**REFERENCE)
    assert not result.was_clamped
    assert not any("raised" in warning.lower() for warning in result.warnings)


@pytest.mark.parametrize("sex", list(Sex))
@pytest.mark.parametrize("activity", list(ActivityLevel))
@pytest.mark.parametrize("goal", list(Goal))
def test_no_combination_ever_falls_below_a_floor(
    sex: Sex, activity: ActivityLevel, goal: Goal
) -> None:
    """The property that must hold for every input, not just the ones we thought of.

    Exhaustive across sex x activity x goal, at a body size small enough to push
    hard against both floors.
    """
    result = calculate_targets(
        sex=sex,
        age_years=65,
        height_cm=150,
        weight_kg=45,
        activity_level=activity,
        goal=goal,
    )
    absolute_floor = MIN_CALORIES_MALE if sex is Sex.MALE else MIN_CALORIES_FEMALE
    assert result.calories >= result.bmr
    assert result.calories >= absolute_floor


# --------------------------------------------------------------------------- #
# Input validation — boundaries
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("age", [MIN_AGE_YEARS, MAX_AGE_YEARS, 30])
def test_ages_inside_the_range_are_accepted(age: int) -> None:
    validate_body_stats(age_years=age, height_cm=170, weight_kg=70)


@pytest.mark.parametrize("age", [MIN_AGE_YEARS - 1, MAX_AGE_YEARS + 1, 0, -5, 500])
def test_ages_outside_the_range_are_rejected(age: int) -> None:
    with pytest.raises(InvalidBodyStats):
        validate_body_stats(age_years=age, height_cm=170, weight_kg=70)


@pytest.mark.parametrize("height", [MIN_HEIGHT_CM, MAX_HEIGHT_CM, 175.0])
def test_heights_inside_the_range_are_accepted(height: float) -> None:
    validate_body_stats(age_years=30, height_cm=height, weight_kg=70)


@pytest.mark.parametrize("height", [MIN_HEIGHT_CM - 0.1, MAX_HEIGHT_CM + 0.1, 17.0, 0.0])
def test_heights_outside_the_range_are_rejected(height: float) -> None:
    """17 cm is the realistic typo — a dropped digit from 170."""
    with pytest.raises(InvalidBodyStats):
        validate_body_stats(age_years=30, height_cm=height, weight_kg=70)


@pytest.mark.parametrize("weight", [MIN_WEIGHT_KG, MAX_WEIGHT_KG, 80.0])
def test_weights_inside_the_range_are_accepted(weight: float) -> None:
    validate_body_stats(age_years=30, height_cm=170, weight_kg=weight)


@pytest.mark.parametrize("weight", [MIN_WEIGHT_KG - 0.1, MAX_WEIGHT_KG + 0.1, 0.0, -70.0])
def test_weights_outside_the_range_are_rejected(weight: float) -> None:
    with pytest.raises(InvalidBodyStats):
        validate_body_stats(age_years=30, height_cm=170, weight_kg=weight)


def test_calculate_targets_validates_before_calculating() -> None:
    """Validation lives in the module, not only at the API boundary."""
    with pytest.raises(InvalidBodyStats):
        calculate_targets(**{**REFERENCE, "height_cm": 17.0})


def test_validation_error_names_the_offending_field() -> None:
    with pytest.raises(InvalidBodyStats, match="Height"):
        validate_body_stats(age_years=30, height_cm=17, weight_kg=70)


# --------------------------------------------------------------------------- #
# Macros
# --------------------------------------------------------------------------- #


def test_protein_is_higher_on_a_cut() -> None:
    """2.2 g/kg cutting versus 1.8 g/kg otherwise — protein protects muscle in a deficit."""
    cutting = calculate_macros(calories=2000, weight_kg=80, goal=Goal.CUT)
    maintaining = calculate_macros(calories=2000, weight_kg=80, goal=Goal.MAINTAIN)
    assert cutting.protein_g == round(2.2 * 80)
    assert maintaining.protein_g == round(1.8 * 80)


def test_reference_macro_split() -> None:
    """2759 kcal at 80 kg maintaining.

    Protein 1.8 x 80 = 144 g. Fat max(0.9 x 80 = 72, 20% of 2759 / 9 = 61.3) = 72 g.
    Remaining 2759 - 576 - 648 = 1535 kcal, so carbs = 1535 / 4 = 384 g.
    """
    macros = calculate_macros(calories=2759, weight_kg=80, goal=Goal.MAINTAIN)
    assert macros.protein_g == 144
    assert macros.fat_g == 72
    assert macros.carbs_g == 384


def test_fat_floor_binds_when_bodyweight_would_give_less() -> None:
    """A light person on a high calorie target.

    45 kg x 0.9 = 40.5 g, but 20% of 3000 kcal / 9 = 66.7 g. The floor wins.
    """
    macros = calculate_macros(calories=3000, weight_kg=45, goal=Goal.BULK)
    assert macros.fat_g == 67
    assert macros.fat_g * KCAL_PER_GRAM_FAT >= 0.20 * 3000


def test_fat_is_never_below_twenty_percent_of_calories() -> None:
    for weight in (30.0, 60.0, 90.0, 150.0, 300.0):
        for calories in (1200, 2000, 3500):
            macros = calculate_macros(calories=calories, weight_kg=weight, goal=Goal.MAINTAIN)
            assert macros.fat_g * KCAL_PER_GRAM_FAT >= 0.20 * calories - KCAL_PER_GRAM_FAT


def test_macros_sum_back_to_the_calorie_target() -> None:
    """Rounding three values to whole grams cannot drift more than a rounding step."""
    for weight in (50.0, 80.0, 120.0):
        for goal in Goal:
            result = calculate_targets(**{**REFERENCE, "weight_kg": weight, "goal": goal})
            drift = abs(result.macros.calories - result.calories)
            assert drift <= KCAL_PER_GRAM_FAT, f"{goal} at {weight} kg drifted {drift} kcal"


def test_macro_calories_property_is_consistent() -> None:
    macros = calculate_macros(calories=2500, weight_kg=75, goal=Goal.MAINTAIN)
    assert macros.calories == (
        macros.protein_g * KCAL_PER_GRAM_PROTEIN
        + macros.carbs_g * KCAL_PER_GRAM_CARBS
        + macros.fat_g * KCAL_PER_GRAM_FAT
    )


def test_carbs_never_go_negative() -> None:
    """Male, 40, 180 cm, 150 kg, sedentary, cut — a genuinely reachable case.

    BMR 2430, so the cut target of 2333 is clamped up to 2430. But protein
    (2.2 x 150 = 330 g = 1320 kcal) plus fat (0.9 x 150 = 135 g = 1215 kcal)
    already comes to 2535 kcal. Carbs floor at zero rather than going negative.
    """
    result = calculate_targets(
        sex=Sex.MALE,
        age_years=40,
        height_cm=180,
        weight_kg=150,
        activity_level=ActivityLevel.SEDENTARY,
        goal=Goal.CUT,
    )
    assert result.macros.carbs_g == 0
    assert any("carbohydrate" in warning.lower() for warning in result.warnings)


def test_all_macros_are_non_negative_across_a_wide_sweep() -> None:
    for weight in (30.0, 60.0, 100.0, 150.0, 250.0, 300.0):
        for goal in Goal:
            for activity in ActivityLevel:
                result = calculate_targets(
                    sex=Sex.MALE,
                    age_years=35,
                    height_cm=175,
                    weight_kg=weight,
                    activity_level=activity,
                    goal=goal,
                )
                assert result.macros.protein_g >= 0
                assert result.macros.carbs_g >= 0
                assert result.macros.fat_g >= 0


# --------------------------------------------------------------------------- #
# Rate-of-change warning
# --------------------------------------------------------------------------- #


def test_warns_when_the_implied_rate_is_too_fast() -> None:
    """Male, 20, 200 cm, 60 kg, very active, cutting.

    BMR 1755, TDEE 3334.5, cut target 2668. The 666 kcal daily deficit implies
    about 0.61 kg a week against a 0.60 kg limit (1% of 60 kg).
    """
    result = calculate_targets(
        sex=Sex.MALE,
        age_years=20,
        height_cm=200,
        weight_kg=60,
        activity_level=ActivityLevel.VERY_ACTIVE,
        goal=Goal.CUT,
    )
    assert any("1%" in warning for warning in result.warnings)


def test_maintenance_never_warns_about_rate() -> None:
    result = calculate_targets(**REFERENCE)
    assert not any("per week" in warning for warning in result.warnings)


def test_moderate_cut_does_not_warn() -> None:
    result = calculate_targets(**{**REFERENCE, "goal": Goal.CUT})
    assert not any("per week" in warning for warning in result.warnings)


# --------------------------------------------------------------------------- #
# Derivation — the explanation shown to the user
# --------------------------------------------------------------------------- #


def test_derivation_covers_the_whole_calculation() -> None:
    result = calculate_targets(**REFERENCE)
    labels = " ".join(step.label.lower() for step in result.derivation)

    for expected in ("basal metabolic rate", "daily expenditure", "protein", "fat", "carbohydrate"):
        assert expected in labels


def test_derivation_reports_the_actual_numbers() -> None:
    """Guards against the explanation drifting away from the maths."""
    result = calculate_targets(**REFERENCE)
    by_label = {step.label: step.value for step in result.derivation}

    assert f"{result.bmr:,}" in by_label["Basal metabolic rate"]
    assert f"{result.tdee:,}" in by_label["Daily expenditure"]
    assert str(result.macros.protein_g) in by_label["Protein"]
    assert str(result.macros.fat_g) in by_label["Fat"]
    assert str(result.macros.carbs_g) in by_label["Carbohydrate"]


def test_derivation_mentions_the_clamp_only_when_clamped() -> None:
    clamped = calculate_targets(
        sex=Sex.FEMALE,
        age_years=70,
        height_cm=150,
        weight_kg=40,
        activity_level=ActivityLevel.SEDENTARY,
        goal=Goal.CUT,
    )
    normal = calculate_targets(**REFERENCE)

    assert any("Raised" in step.label for step in clamped.derivation)
    assert not any("Raised" in step.label for step in normal.derivation)


def test_results_are_immutable() -> None:
    """Frozen dataclasses: a caller cannot quietly edit a target after the fact."""
    result = calculate_targets(**REFERENCE)
    with pytest.raises(AttributeError):
        result.calories = 9999  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Rate of change (item 8: the user picks how fast)
# --------------------------------------------------------------------------- #


def test_rate_produces_the_deficit_the_arithmetic_implies() -> None:
    """0.5 kg a week is 7700/2 kcal over seven days = 550 kcal a day."""
    steady = calculate_targets(
        sex=Sex.MALE,
        age_years=30,
        height_cm=180,
        weight_kg=80,
        activity_level=ActivityLevel.MODERATE,
        goal=Goal.MAINTAIN,
        weekly_rate_kg=0,
    )
    cutting = calculate_targets(
        sex=Sex.MALE,
        age_years=30,
        height_cm=180,
        weight_kg=80,
        activity_level=ActivityLevel.MODERATE,
        goal=Goal.CUT,
        weekly_rate_kg=0.5,
    )

    assert steady.calories == steady.tdee
    assert steady.tdee - cutting.uncapped_calories == pytest.approx(550, abs=1)


def test_direction_comes_from_the_goal_not_the_sign() -> None:
    """The user picks "how fast", never "which way" — a negative rate would be a
    second, contradictory source of truth about direction."""
    common = dict(
        sex=Sex.MALE,
        age_years=30,
        height_cm=180,
        weight_kg=80,
        activity_level=ActivityLevel.MODERATE,
        weekly_rate_kg=0.5,
    )
    cutting = calculate_targets(goal=Goal.CUT, **common)
    bulking = calculate_targets(goal=Goal.BULK, **common)

    assert cutting.uncapped_calories < cutting.tdee < bulking.uncapped_calories
    # Symmetrical about maintenance: same rate, opposite directions.
    assert (cutting.tdee - cutting.uncapped_calories) == pytest.approx(
        bulking.uncapped_calories - bulking.tdee, abs=1
    )


def test_a_negative_rate_is_rejected() -> None:
    with pytest.raises(InvalidBodyStats, match="cannot be negative"):
        calculate_targets(
            sex=Sex.MALE,
            age_years=30,
            height_cm=180,
            weight_kg=80,
            activity_level=ActivityLevel.MODERATE,
            goal=Goal.CUT,
            weekly_rate_kg=-0.5,
        )


def test_an_absurd_rate_is_refused_rather_than_planned_for() -> None:
    """The arithmetic keeps working past this point; the answer stops being
    something an app should hand someone."""
    with pytest.raises(InvalidBodyStats, match="beyond the"):
        calculate_targets(
            sex=Sex.MALE,
            age_years=30,
            height_cm=180,
            weight_kg=80,
            activity_level=ActivityLevel.MODERATE,
            goal=Goal.CUT,
            weekly_rate_kg=3.0,
        )


def test_an_aggressive_rate_still_hits_the_safety_floor() -> None:
    """The rate model must not become a way around the clamp that the
    percentage model was subject to."""
    result = calculate_targets(
        sex=Sex.FEMALE,
        age_years=30,
        height_cm=160,
        weight_kg=55,
        activity_level=ActivityLevel.SEDENTARY,
        goal=Goal.CUT,
        weekly_rate_kg=1.5,
    )

    assert result.was_clamped
    assert result.calories >= MIN_CALORIES_FEMALE
    assert result.warnings


def test_omitting_the_rate_keeps_the_old_multiplier_behaviour() -> None:
    """Profiles saved before the picker existed must not have their targets move.

    This is the whole reason the column is nullable rather than backfilled.
    """
    common = dict(
        sex=Sex.MALE,
        age_years=30,
        height_cm=180,
        weight_kg=80,
        activity_level=ActivityLevel.MODERATE,
        goal=Goal.CUT,
    )

    assert calculate_targets(**common).calories == round(
        calculate_targets(**common).tdee * GOAL_MULTIPLIERS[Goal.CUT]
    )


def test_the_derivation_explains_the_rate_rather_than_a_multiplier() -> None:
    """The derivation must describe the calculation that actually ran."""
    result = calculate_targets(
        sex=Sex.MALE,
        age_years=30,
        height_cm=180,
        weight_kg=80,
        activity_level=ActivityLevel.MODERATE,
        goal=Goal.CUT,
        weekly_rate_kg=0.75,
    )

    labels = [step.label for step in result.derivation]
    assert "0.75 kg per week" in labels
    assert not any("x 0.80" in step.detail for step in result.derivation)


def test_rate_scales_with_the_person_where_a_percentage_does_not() -> None:
    """The reason the rate model is better.

    A 20% deficit is a much larger absolute cut for a big person than a small
    one, though both tapped the same button. A rate means the same thing to both.
    """
    small = calculate_targets(
        sex=Sex.FEMALE,
        age_years=30,
        height_cm=155,
        weight_kg=50,
        activity_level=ActivityLevel.LIGHT,
        goal=Goal.CUT,
        weekly_rate_kg=0.5,
    )
    large = calculate_targets(
        sex=Sex.MALE,
        age_years=30,
        height_cm=195,
        weight_kg=110,
        activity_level=ActivityLevel.LIGHT,
        goal=Goal.CUT,
        weekly_rate_kg=0.5,
    )

    assert (small.tdee - small.uncapped_calories) == pytest.approx(
        large.tdee - large.uncapped_calories, abs=1
    )


def test_maintain_ignores_any_rate_it_is_given() -> None:
    """"Maintain, at 0.5 kg a week" is incoherent; the goal wins."""
    result = calculate_targets(
        sex=Sex.MALE,
        age_years=30,
        height_cm=180,
        weight_kg=80,
        activity_level=ActivityLevel.MODERATE,
        goal=Goal.MAINTAIN,
        weekly_rate_kg=0.5,
    )

    assert result.calories == result.tdee


def test_every_goal_has_a_default_rate() -> None:
    """Onboarding needs somewhere to open the picker for each goal."""
    for goal in Goal:
        assert goal in DEFAULT_WEEKLY_RATE_KG
        assert 0 <= DEFAULT_WEEKLY_RATE_KG[goal] <= MAX_WEEKLY_RATE_KG
