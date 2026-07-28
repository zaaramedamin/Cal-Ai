"""Browsing the catalogue and logging from it.

The unit conversion is the thing under test. Everything else in these endpoints
is a lookup; the conversion is where a wrong number would be plausible enough to
survive review and permanent enough to poison every day it appears in.
"""

import pytest
from fastapi.testclient import TestClient

from app.schemas.catalogue import CatalogueFood, Portion, UnitKind
from app.services.catalogue import format_amount, grams_for, nutrients_for

PROFILE = {
    "sex": "male",
    "birth_date": "1996-05-20",
    "height_cm": 180,
    "weight_kg": 80,
    "activity_level": "moderate",
    "goal": "maintain",
    "timezone": "UTC",
}


def onboarded(client: TestClient, email: str = "browser@example.com") -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.put("/api/v1/profile", json=PROFILE, headers=headers)
    return headers


def food(**overrides) -> CatalogueFood:
    defaults = dict(
        slug="test",
        name_en="Test",
        name_fr="Test",
        category="Protein",
        emoji="🍽",
        unit=UnitKind.GRAMS,
        grams_per_unit=1.0,
        kcal=100,
        protein_g=10,
        carbs_g=5,
        fat_g=2,
        portions=[Portion(label_en="1", label_fr="1", amount=100, grams=100, is_default=True)],
    )
    return CatalogueFood(**{**defaults, **overrides})


# --------------------------------------------------------------------------- #
# The conversion, in isolation
# --------------------------------------------------------------------------- #


def test_grams_food_converts_one_to_one() -> None:
    assert grams_for(food(unit=UnitKind.GRAMS, grams_per_unit=1.0), 150) == 150


def test_countable_food_multiplies_by_item_weight() -> None:
    """The conversion the whole catalogue exists for: the user picks 2, the
    diary receives 100 g."""
    assert grams_for(food(unit=UnitKind.COUNT, grams_per_unit=50), 2) == 100


def test_liquid_food_uses_its_own_density_not_water() -> None:
    """250 ml of milk is 257.5 g, not 250 g.

    Assuming water here is a 3% error on milk and a 9% error on olive oil — and
    on oil that lands on the most calorie-dense food in the catalogue, where it
    is worth roughly 12 kcal a spoonful and looks entirely normal.
    """
    assert grams_for(food(unit=UnitKind.MILLILITRES, grams_per_unit=1.03), 250) == 257.5
    assert grams_for(food(unit=UnitKind.MILLILITRES, grams_per_unit=0.91), 15) == pytest.approx(
        13.65
    )


def test_arbitrary_amounts_convert_without_a_matching_portion() -> None:
    """The reason `grams_per_unit` exists on every food rather than only on
    countables.

    A user typing 300 ml when the portion list offers 250 and 1000 must still get
    a correct weight. When the conversion lived only in the portion list this was
    unanswerable, and the tempting fallback — treat it as water — is the exact
    error the density is there to prevent.
    """
    milk = food(
        unit=UnitKind.MILLILITRES,
        grams_per_unit=1.03,
        portions=[Portion(label_en="1 glass", label_fr="1 verre", amount=250, grams=257.5)],
    )

    assert grams_for(milk, 300) == 309.0


def test_missing_nutrients_survive_scaling_as_missing() -> None:
    """A food with no fibre figure has no fibre figure at 150 g either."""
    scaled = nutrients_for(food(fibre_g=None, sodium_mg=40), 150)

    assert scaled["fibre_g"] is None
    assert scaled["kcal"] == 150.0
    assert scaled["sodium_mg"] == 60.0


def test_amount_reads_back_in_the_users_own_unit() -> None:
    assert format_amount(food(unit=UnitKind.GRAMS), 150) == "150 g"
    assert format_amount(food(unit=UnitKind.MILLILITRES), 250) == "250 ml"
    assert format_amount(food(unit=UnitKind.COUNT, name_en="Egg"), 2) == "2 × egg"
    # Whole numbers must not print as "2.0", and halves must survive.
    assert format_amount(food(unit=UnitKind.COUNT, name_en="Avocado"), 0.5) == "0.5 × avocado"


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


def test_browse_groups_foods_into_ordered_sections(client: TestClient, catalogue) -> None:
    headers = onboarded(client)

    body = client.get("/api/v1/catalogue", headers=headers).json()

    assert body["total"] == 2
    # Protein before Dairy — the curated order, not the alphabet.
    assert [section["category"] for section in body["sections"]] == ["Protein", "Dairy"]
    assert body["sections"][0]["foods"][0]["slug"] == "egg"


def test_browse_carries_both_languages(client: TestClient, catalogue) -> None:
    """So switching language in Settings re-renders instead of refetching."""
    headers = onboarded(client)

    egg = client.get("/api/v1/catalogue", headers=headers).json()["sections"][0]["foods"][0]

    assert egg["name_en"] == "Egg"
    assert egg["name_fr"] == "Œuf"
    assert egg["portions"][1]["label_fr"] == "2 œufs"


def test_browse_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/catalogue").status_code == 401


def test_unknown_slug_is_a_404(client: TestClient, catalogue) -> None:
    headers = onboarded(client)

    assert client.get("/api/v1/catalogue/pangolin", headers=headers).status_code == 404


def test_slug_pattern_rejects_query_operators(client: TestClient, catalogue) -> None:
    """A path parameter that reaches a Mongo filter must not be able to *be* a
    filter. `[a-z0-9-]` cannot express `$ne`, so the injection has nowhere to go
    — and FastAPI rejects it before the query is built at all."""
    headers = onboarded(client)

    response = client.get('/api/v1/catalogue/{"$ne":null}', headers=headers)

    assert response.status_code == 422


def test_logging_two_eggs_records_one_hundred_grams(client: TestClient, catalogue) -> None:
    """End to end: the user picks 2, the diary stores 100 g and 143 kcal."""
    headers = onboarded(client)

    response = client.post(
        "/api/v1/catalogue/egg/log",
        json={"amount": 2, "meal_slot": "breakfast"},
        headers=headers,
    )

    assert response.status_code == 201
    entry = response.json()
    assert entry["quantity_grams"] == 100.0
    assert entry["kcal"] == 143.0
    assert entry["protein_g"] == pytest.approx(12.6)


def test_logged_entry_names_the_portion_the_user_chose(client: TestClient, catalogue) -> None:
    """History should read "2 × egg", not "100 g"."""
    headers = onboarded(client)

    entry = client.post(
        "/api/v1/catalogue/egg/log",
        json={"amount": 2, "meal_slot": "breakfast"},
        headers=headers,
    ).json()

    assert entry["food_name"] == "Egg (2 × egg)"


def test_logging_a_liquid_applies_density(client: TestClient, catalogue) -> None:
    headers = onboarded(client)

    entry = client.post(
        "/api/v1/catalogue/milk/log",
        json={"amount": 250, "meal_slot": "snack"},
        headers=headers,
    ).json()

    assert entry["quantity_grams"] == 257.5
    assert entry["kcal"] == pytest.approx(157.08, abs=0.01)


def test_logged_food_is_linked_to_a_real_food_row(client: TestClient, catalogue) -> None:
    """A catalogue food materialises into `foods` keyed on its FDC id.

    Without the link, everything built on `food_id` — quick-add, food detail,
    suggestions — silently stops seeing anything logged from the catalogue.
    """
    headers = onboarded(client)

    entry = client.post(
        "/api/v1/catalogue/egg/log",
        json={"amount": 1, "meal_slot": "breakfast"},
        headers=headers,
    ).json()

    assert entry["food_id"] is not None
    detail = client.get(f"/api/v1/foods/{entry['food_id']}", headers=headers).json()
    assert detail["source"] == "usda"
    assert detail["source_id"] == "748967"


def test_logging_the_same_food_twice_reuses_one_food_row(
    client: TestClient, catalogue
) -> None:
    """The upsert is keyed on (source, source_id), so repeats converge rather
    than littering the table."""
    headers = onboarded(client)

    first = client.post(
        "/api/v1/catalogue/egg/log", json={"amount": 1, "meal_slot": "breakfast"}, headers=headers
    ).json()
    second = client.post(
        "/api/v1/catalogue/egg/log", json={"amount": 3, "meal_slot": "lunch"}, headers=headers
    ).json()

    assert first["food_id"] == second["food_id"]


def test_logged_catalogue_food_reaches_the_diary(client: TestClient, catalogue) -> None:
    headers = onboarded(client)
    client.post(
        "/api/v1/catalogue/egg/log", json={"amount": 2, "meal_slot": "breakfast"}, headers=headers
    )

    day = client.get("/api/v1/diary", headers=headers).json()

    assert day["totals"]["kcal"] == 143.0


def test_cannot_log_to_a_future_date(client: TestClient, catalogue) -> None:
    headers = onboarded(client)

    response = client.post(
        "/api/v1/catalogue/egg/log",
        json={"amount": 1, "meal_slot": "breakfast", "day": "2099-01-01"},
        headers=headers,
    )

    assert response.status_code == 422


def test_zero_and_negative_amounts_are_rejected(client: TestClient, catalogue) -> None:
    headers = onboarded(client)

    for amount in (0, -1):
        response = client.post(
            "/api/v1/catalogue/egg/log",
            json={"amount": amount, "meal_slot": "breakfast"},
            headers=headers,
        )
        assert response.status_code == 422
