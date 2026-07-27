"""USDA payload normalisation.

Pure tests over recorded payload shapes — no network. These are the tests that
enforce "never invent a nutrition value", because every rule they check is one
where a naive implementation silently produces a wrong number instead of an
error.
"""

import pytest

from app.services.usda import UnusableFood, normalise_food


def payload(**overrides):
    base = {
        "fdcId": 173944,
        "description": "Banana, raw",
        "dataType": "Foundation",
        "foodNutrients": [
            {"nutrient": {"number": "1008"}, "amount": 89.0},
            {"nutrient": {"number": "1003"}, "amount": 1.09},
            {"nutrient": {"number": "1005"}, "amount": 22.84},
            {"nutrient": {"number": "1004"}, "amount": 0.33},
        ],
    }
    return {**base, **overrides}


def test_normalises_a_foundation_food() -> None:
    food = normalise_food(payload())
    assert food["source"] == "usda"
    assert food["source_id"] == "173944"
    assert food["name"] == "Banana, raw"
    assert food["kcal"] == 89.0
    assert food["protein_g"] == 1.09


def test_missing_nutrients_stay_none_rather_than_zero() -> None:
    """The single most important assertion in this file.

    USDA Foundation entries genuinely omit fibre. Defaulting it to 0 would tell
    the user wholemeal bread contains no fibre, with no way for them to know the
    number was fabricated by our import.
    """
    food = normalise_food(payload())
    assert food["fibre_g"] is None
    assert food["sugars_g"] is None
    assert food["saturated_fat_g"] is None
    assert food["sodium_mg"] is None


def test_optional_nutrients_are_kept_when_present() -> None:
    food = normalise_food(
        payload(
            foodNutrients=[
                *payload()["foodNutrients"],
                {"nutrient": {"number": "1079"}, "amount": 2.6},
                {"nutrient": {"number": "1093"}, "amount": 1.0},
            ]
        )
    )
    assert food["fibre_g"] == 2.6
    assert food["sodium_mg"] == 1.0


# --------------------------------------------------------------------------- #
# Energy fallbacks
# --------------------------------------------------------------------------- #


def test_falls_back_to_kilojoules() -> None:
    """Some Foundation foods report only kJ. 372.4 / 4.184 = 89.0 kcal.

    An exact unit conversion, not an estimate — which is why it is allowed where
    guessing is not.
    """
    food = normalise_food(
        payload(
            foodNutrients=[
                {"nutrient": {"number": "1062"}, "amount": 372.4},
                {"nutrient": {"number": "1003"}, "amount": 1.09},
                {"nutrient": {"number": "1005"}, "amount": 22.84},
                {"nutrient": {"number": "1004"}, "amount": 0.33},
            ]
        )
    )
    assert food["kcal"] == pytest.approx(89.0, abs=0.1)


def test_falls_back_to_atwater_energy() -> None:
    food = normalise_food(
        payload(
            foodNutrients=[
                {"nutrient": {"number": "2048"}, "amount": 95.0},
                {"nutrient": {"number": "1003"}, "amount": 1.09},
                {"nutrient": {"number": "1005"}, "amount": 22.84},
                {"nutrient": {"number": "1004"}, "amount": 0.33},
            ]
        )
    )
    assert food["kcal"] == 95.0


def test_food_with_no_energy_is_rejected() -> None:
    """Rejected, never estimated from macros. A calculated calorie count would
    look identical to a measured one and be unattributable."""
    with pytest.raises(UnusableFood, match="energy"):
        normalise_food(
            payload(
                foodNutrients=[
                    {"nutrient": {"number": "1003"}, "amount": 1.09},
                    {"nutrient": {"number": "1005"}, "amount": 22.84},
                    {"nutrient": {"number": "1004"}, "amount": 0.33},
                ]
            )
        )


@pytest.mark.parametrize("missing", ["1003", "1005", "1004"])
def test_food_missing_a_required_macro_is_rejected(missing: str) -> None:
    nutrients = [n for n in payload()["foodNutrients"] if n["nutrient"]["number"] != missing]
    with pytest.raises(UnusableFood):
        normalise_food(payload(foodNutrients=nutrients))


def test_food_without_a_description_is_rejected() -> None:
    with pytest.raises(UnusableFood, match="description"):
        normalise_food(payload(description="  "))


# --------------------------------------------------------------------------- #
# Branded foods are per serving, not per 100 g
# --------------------------------------------------------------------------- #


def test_branded_food_nutrients_are_never_scaled() -> None:
    """Regression test for a bug that live data caught and a unit test did not.

    `foodNutrients` is per 100 g for *every* data type — USDA normalises it,
    Branded included. An earlier version scaled it by serving size on the
    assumption that Branded was per serving, which turned an 89 kcal banana with
    a 32 g serving into 975 kcal.

    The original test asserted that same wrong assumption, so it passed happily
    while the code was wrong. Only a real API response exposed it.
    """
    food = normalise_food(
        payload(
            dataType="Branded",
            servingSize=32,
            servingSizeUnit="g",
            brandOwner="Some Fruit Co",
            foodNutrients=[
                {"nutrientId": 1008, "nutrientNumber": "208", "value": 89.0},
                {"nutrientId": 1003, "nutrientNumber": "203", "value": 1.09},
                {"nutrientId": 1005, "nutrientNumber": "205", "value": 22.84},
                {"nutrientId": 1004, "nutrientNumber": "204", "value": 0.33},
            ],
        )
    )
    assert food["kcal"] == 89.0, "per-100g values must pass through untouched"
    assert food["protein_g"] == 1.09
    assert food["brand"] == "Some Fruit Co"


def test_search_results_use_legacy_nutrient_numbers() -> None:
    """The other half of the same bug.

    `/foods/search` returns `nutrientNumber` as the legacy INFOODS tagname —
    protein is 203 there and 1003 in detail responses. Reading only
    `nutrientNumber` matched nothing, so every search result was rejected as
    having no energy, which looked like bad data from USDA rather than our bug.
    """
    food = normalise_food(
        payload(
            foodNutrients=[
                {"nutrientId": 1008, "nutrientNumber": "208", "value": 312.0},
                {"nutrientId": 1003, "nutrientNumber": "203", "value": 12.5},
                {"nutrientId": 1005, "nutrientNumber": "205", "value": 50.0},
                {"nutrientId": 1004, "nutrientNumber": "204", "value": 10.0},
            ]
        )
    )
    assert food["kcal"] == 312.0
    assert food["protein_g"] == 12.5


def test_label_nutrients_fill_gaps_and_are_scaled_to_per_100g() -> None:
    """`labelNutrients` IS per serving, and is the only thing scaled.

    200 kcal per 55 g serving is 363.64 per 100 g. Used only when
    `foodNutrients` lacks the value, since USDA's own per-100 g figure is more
    trustworthy than one derived from a rounded label.
    """
    food = normalise_food(
        payload(
            dataType="Branded",
            servingSize=55,
            servingSizeUnit="g",
            foodNutrients=[],
            labelNutrients={
                "calories": {"value": 200.0},
                "protein": {"value": 5.0},
                "carbohydrates": {"value": 40.0},
                "fat": {"value": 2.0},
            },
        )
    )
    assert food["kcal"] == pytest.approx(363.64, abs=0.01)
    assert food["protein_g"] == pytest.approx(9.09, abs=0.01)


def test_food_nutrients_win_over_label_nutrients() -> None:
    food = normalise_food(
        payload(
            dataType="Branded",
            servingSize=55,
            servingSizeUnit="g",
            labelNutrients={"calories": {"value": 200.0}},
        )
    )
    assert food["kcal"] == 89.0


def test_label_nutrients_are_ignored_without_a_convertible_serving() -> None:
    """A serving in cups cannot be converted without a density, and guessing one
    would be inventing data."""
    with pytest.raises(UnusableFood, match="energy"):
        normalise_food(
            payload(
                dataType="Branded",
                servingSize=1,
                servingSizeUnit="cup",
                foodNutrients=[],
                labelNutrients={"calories": {"value": 200.0}},
            )
        )


# --------------------------------------------------------------------------- #
# Payload shape tolerance
# --------------------------------------------------------------------------- #


def test_handles_the_flattened_nutrient_shape() -> None:
    """Search results use `nutrientNumber` where detail responses nest under
    `nutrient`. Both have to work or search results silently lose nutrients."""
    food = normalise_food(
        payload(
            foodNutrients=[
                {"nutrientNumber": "1008", "value": 89.0},
                {"nutrientNumber": "1003", "value": 1.09},
                {"nutrientNumber": "1005", "value": 22.84},
                {"nutrientNumber": "1004", "value": 0.33},
            ]
        )
    )
    assert food["kcal"] == 89.0
    assert food["carbs_g"] == 22.84


def test_ignores_malformed_nutrient_entries() -> None:
    food = normalise_food(
        payload(
            foodNutrients=[
                *payload()["foodNutrients"],
                {"nutrient": {"number": "1079"}, "amount": None},
                {"nutrient": {}, "amount": 5},
                "not-a-dict",
            ]
        )
    )
    assert food["fibre_g"] is None


# --------------------------------------------------------------------------- #
# Portions
# --------------------------------------------------------------------------- #


def test_extracts_portions_with_gram_weights() -> None:
    food = normalise_food(
        payload(
            foodPortions=[
                {"amount": 1, "measureUnit": {"name": "medium"}, "gramWeight": 118.0},
                {"amount": 1, "measureUnit": {"name": "cup"}, "modifier": "sliced",
                 "gramWeight": 150.0},
            ]
        )
    )
    labels = {portion["label"]: portion["grams"] for portion in food["portions"]}
    assert labels["1 medium"] == 118.0
    assert labels["1 cup sliced"] == 150.0


def test_skips_portions_without_a_gram_weight() -> None:
    """A label with no weight cannot become a nutrient calculation, and offering
    it would invite the user to log a number we would have to invent."""
    food = normalise_food(
        payload(
            foodPortions=[
                {"amount": 1, "measureUnit": {"name": "serving"}},
                {"amount": 1, "measureUnit": {"name": "medium"}, "gramWeight": 118.0},
            ]
        )
    )
    assert len(food["portions"]) == 1
    assert food["portions"][0]["grams"] == 118.0
