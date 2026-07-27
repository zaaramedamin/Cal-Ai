"""Recipe nutrition and endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.food import Food
from app.nutrition.recipes import IngredientNutrition, calculate_recipe_nutrition

PROFILE = {
    "sex": "male",
    "birth_date": "1996-05-20",
    "height_cm": 180,
    "weight_kg": 80,
    "activity_level": "moderate",
    "goal": "maintain",
    "timezone": "UTC",
}


# --------------------------------------------------------------------------- #
# The pure calculation
# --------------------------------------------------------------------------- #


def test_sums_ingredients_and_divides_by_servings() -> None:
    """200 g at 165 kcal/100 g plus 100 g at 350 kcal/100 g = 680 kcal, over 4
    servings = 170 each."""
    nutrition = calculate_recipe_nutrition(
        [
            IngredientNutrition(grams=200, kcal=165, protein_g=31, carbs_g=0, fat_g=3.6),
            IngredientNutrition(grams=100, kcal=350, protein_g=13, carbs_g=72, fat_g=1.5),
        ],
        servings=4,
    )
    assert nutrition.total_grams == 300
    assert nutrition.total["kcal"] == 680.0
    assert nutrition.per_serving["kcal"] == 170.0
    assert nutrition.per_serving["protein_g"] == pytest.approx(18.75)


def test_missing_nutrients_make_a_total_partial() -> None:
    """One ingredient reports fibre, one does not. The sum is a floor, and says so."""
    nutrition = calculate_recipe_nutrition(
        [
            IngredientNutrition(grams=100, kcal=100, protein_g=1, carbs_g=1, fat_g=1, fibre_g=10),
            IngredientNutrition(grams=100, kcal=100, protein_g=1, carbs_g=1, fat_g=1),
        ],
        servings=1,
    )
    assert nutrition.total["fibre_g"] == 10.0
    assert "fibre_g" in nutrition.partial


def test_a_nutrient_no_ingredient_reports_is_none_not_zero() -> None:
    nutrition = calculate_recipe_nutrition(
        [IngredientNutrition(grams=100, kcal=100, protein_g=1, carbs_g=1, fat_g=1)],
        servings=1,
    )
    assert nutrition.total["fibre_g"] is None
    assert nutrition.per_serving["fibre_g"] is None


def test_rounding_happens_once_at_the_end() -> None:
    """Rounding each ingredient before summing accumulates error.

    Twelve ingredients at 33.333 kcal each is 400 exactly; rounding each to 33
    first gives 396 — visibly different from the sum of what the user was shown.
    """
    nutrition = calculate_recipe_nutrition(
        [
            IngredientNutrition(grams=100, kcal=33.333, protein_g=0, carbs_g=0, fat_g=0)
            for _ in range(12)
        ],
        servings=1,
    )
    assert nutrition.total["kcal"] == 400.0


def test_zero_servings_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one serving"):
        calculate_recipe_nutrition([], servings=0)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


async def make_food(session: AsyncSession, source_id: str, name: str, **overrides) -> Food:
    food = Food(
        source="usda",
        source_id=source_id,
        name=name,
        kcal=overrides.pop("kcal", 165),
        protein_g=overrides.pop("protein_g", 31),
        carbs_g=overrides.pop("carbs_g", 0),
        fat_g=overrides.pop("fat_g", 3.6),
        fibre_g=overrides.pop("fibre_g", None),
        **overrides,
    )
    session.add(food)
    await session.commit()
    await session.refresh(food)
    return food


def onboarded(client: TestClient, email: str = "chef@example.com") -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.put("/api/v1/profile", json=PROFILE, headers=headers)
    return headers


async def test_create_and_read_a_recipe(client: TestClient, session: AsyncSession) -> None:
    chicken = await make_food(session, "r1", "Chicken breast")
    rice = await make_food(session, "r2", "Rice", kcal=350, protein_g=13, carbs_g=72, fat_g=1.5)
    headers = onboarded(client)

    response = client.post(
        "/api/v1/recipes",
        json={
            "name": "Chicken and rice",
            "servings": 4,
            "ingredients": [
                {"food_id": str(chicken.id), "grams": 200},
                {"food_id": str(rice.id), "grams": 100},
            ],
        },
        headers=headers,
    )

    assert response.status_code == 201
    recipe = response.json()
    assert recipe["name"] == "Chicken and rice"
    assert len(recipe["ingredients"]) == 2
    assert recipe["total"]["kcal"] == 680.0
    assert recipe["per_serving"]["kcal"] == 170.0


async def test_ingredient_order_is_preserved(client: TestClient, session: AsyncSession) -> None:
    """The order things were added usually mirrors the order they are used.
    Sorting alphabetically would scramble a method."""
    first = await make_food(session, "r1", "Zucchini")
    second = await make_food(session, "r2", "Apple")
    headers = onboarded(client)

    recipe = client.post(
        "/api/v1/recipes",
        json={
            "name": "Odd salad",
            "servings": 1,
            "ingredients": [
                {"food_id": str(first.id), "grams": 100},
                {"food_id": str(second.id), "grams": 50},
            ],
        },
        headers=headers,
    ).json()

    assert [item["food_name"] for item in recipe["ingredients"]] == ["Zucchini", "Apple"]


async def test_duplicate_ingredient_is_rejected(
    client: TestClient, session: AsyncSession
) -> None:
    """Adding the same food twice is invisible in a list and silently doubles a total."""
    food = await make_food(session, "r1", "Chicken")
    headers = onboarded(client)

    response = client.post(
        "/api/v1/recipes",
        json={
            "name": "Double chicken",
            "servings": 1,
            "ingredients": [
                {"food_id": str(food.id), "grams": 100},
                {"food_id": str(food.id), "grams": 50},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_unknown_food_is_rejected(client: TestClient) -> None:
    headers = onboarded(client)
    response = client.post(
        "/api/v1/recipes",
        json={
            "name": "Ghost stew",
            "servings": 1,
            "ingredients": [
                {"food_id": "00000000-0000-0000-0000-000000000001", "grams": 100}
            ],
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_recipe_with_no_ingredients_is_rejected(client: TestClient) -> None:
    headers = onboarded(client)
    response = client.post(
        "/api/v1/recipes",
        json={"name": "Empty", "servings": 1, "ingredients": []},
        headers=headers,
    )
    assert response.status_code == 422


async def test_recipes_are_isolated_between_users(
    client: TestClient, session: AsyncSession
) -> None:
    food = await make_food(session, "r1", "Chicken")
    alice = onboarded(client, "alice-chef@example.com")
    bob = onboarded(client, "bob-chef@example.com")

    recipe = client.post(
        "/api/v1/recipes",
        json={
            "name": "Alice's stew",
            "servings": 2,
            "ingredients": [{"food_id": str(food.id), "grams": 300}],
        },
        headers=alice,
    ).json()

    assert client.get(f"/api/v1/recipes/{recipe['id']}", headers=bob).status_code == 404
    assert client.delete(f"/api/v1/recipes/{recipe['id']}", headers=bob).status_code == 404
    assert client.get("/api/v1/recipes", headers=bob).json() == []


async def test_editing_a_recipe_replaces_ingredients(
    client: TestClient, session: AsyncSession
) -> None:
    butter = await make_food(session, "r1", "Butter", kcal=717, protein_g=0.9, carbs_g=0, fat_g=81)
    oil = await make_food(session, "r2", "Olive oil", kcal=884, protein_g=0, carbs_g=0, fat_g=100)
    headers = onboarded(client)

    recipe = client.post(
        "/api/v1/recipes",
        json={
            "name": "Sunday chilli",
            "servings": 1,
            "ingredients": [{"food_id": str(butter.id), "grams": 100}],
        },
        headers=headers,
    ).json()

    updated = client.put(
        f"/api/v1/recipes/{recipe['id']}",
        json={
            "name": "Sunday chilli",
            "servings": 1,
            "ingredients": [{"food_id": str(oil.id), "grams": 100}],
        },
        headers=headers,
    ).json()

    assert len(updated["ingredients"]) == 1
    assert updated["ingredients"][0]["food_name"] == "Olive oil"
    assert updated["total"]["kcal"] == 884.0


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #


async def test_logging_a_recipe_snapshots_the_portion(
    client: TestClient, session: AsyncSession
) -> None:
    food = await make_food(session, "r1", "Chicken")
    headers = onboarded(client)

    recipe = client.post(
        "/api/v1/recipes",
        json={
            "name": "Chicken tray",
            "servings": 4,
            "ingredients": [{"food_id": str(food.id), "grams": 400}],
        },
        headers=headers,
    ).json()

    response = client.post(
        f"/api/v1/recipes/{recipe['id']}/log?meal_slot=dinner",
        json={"servings": 1},
        headers=headers,
    )

    assert response.status_code == 201
    entry = response.json()
    # 400 g at 165 kcal/100 g = 660 kcal total, over 4 servings = 165 each.
    assert entry["kcal"] == 165.0
    assert entry["servings"] == 1.0
    assert entry["quantity_grams"] == 100.0
    assert entry["food_name"] == "Chicken tray"


async def test_editing_a_recipe_does_not_rewrite_logged_meals(
    client: TestClient, session: AsyncSession
) -> None:
    """The claim that makes snapshotting worth its duplication.

    Swap butter for oil in your Sunday chilli and every portion you ever logged
    would otherwise change retroactively.
    """
    butter = await make_food(session, "r1", "Butter", kcal=717, protein_g=0.9, carbs_g=0, fat_g=81)
    oil = await make_food(session, "r2", "Olive oil", kcal=884, protein_g=0, carbs_g=0, fat_g=100)
    headers = onboarded(client)

    recipe = client.post(
        "/api/v1/recipes",
        json={
            "name": "Sunday chilli",
            "servings": 1,
            "ingredients": [{"food_id": str(butter.id), "grams": 100}],
        },
        headers=headers,
    ).json()

    client.post(
        f"/api/v1/recipes/{recipe['id']}/log?meal_slot=dinner",
        json={"servings": 1},
        headers=headers,
    )

    client.put(
        f"/api/v1/recipes/{recipe['id']}",
        json={
            "name": "Sunday chilli",
            "servings": 1,
            "ingredients": [{"food_id": str(oil.id), "grams": 100}],
        },
        headers=headers,
    )

    day = client.get("/api/v1/diary", headers=headers).json()
    assert day["totals"]["kcal"] == 717.0, "the logged meal must keep butter's numbers"


async def test_deleting_a_recipe_keeps_the_logged_meal(
    client: TestClient, session: AsyncSession
) -> None:
    food = await make_food(session, "r1", "Chicken")
    headers = onboarded(client)

    recipe = client.post(
        "/api/v1/recipes",
        json={
            "name": "Chicken tray",
            "servings": 2,
            "ingredients": [{"food_id": str(food.id), "grams": 200}],
        },
        headers=headers,
    ).json()

    client.post(
        f"/api/v1/recipes/{recipe['id']}/log?meal_slot=lunch",
        json={"servings": 1},
        headers=headers,
    )
    assert client.delete(f"/api/v1/recipes/{recipe['id']}", headers=headers).status_code == 204

    day = client.get("/api/v1/diary", headers=headers).json()
    entries = [entry for meal in day["meals"] for entry in meal["entries"]]
    assert len(entries) == 1
    assert entries[0]["food_name"] == "Chicken tray"
    assert entries[0]["recipe_id"] is None


async def test_half_servings_scale_correctly(
    client: TestClient, session: AsyncSession
) -> None:
    food = await make_food(session, "r1", "Chicken")
    headers = onboarded(client)

    recipe = client.post(
        "/api/v1/recipes",
        json={
            "name": "Tray",
            "servings": 2,
            "ingredients": [{"food_id": str(food.id), "grams": 200}],
        },
        headers=headers,
    ).json()

    entry = client.post(
        f"/api/v1/recipes/{recipe['id']}/log?meal_slot=lunch",
        json={"servings": 0.5},
        headers=headers,
    ).json()

    # 200 g at 165 = 330 total, 165 per serving, half of that is 82.5.
    assert entry["kcal"] == 82.5
    assert entry["quantity_grams"] == 50.0


def test_recipes_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/recipes").status_code == 401
    assert client.post("/api/v1/recipes", json={}).status_code == 401
