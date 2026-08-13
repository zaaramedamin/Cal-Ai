"""Barcode lookup against Open Food Facts.

The cases that matter are the dishonest ones. Open Food Facts is crowd-sourced,
so a great many records are a name and a photograph with no nutrition at all —
and storing one of those as a food with 0 kcal would look like a working scan
while putting a wrong number straight into someone's diary.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.v1.foods import get_off_client
from app.main import app
from app.services.openfoodfacts import (
    OffUnavailable,
    ProductNotFound,
    UnusableProduct,
    normalise_product,
)

COMPLETE = {
    "code": "3017620422003",
    "product_name": "Nutella",
    "brands": "Ferrero,Nutella",
    "nutriments": {
        "energy-kcal_100g": 539,
        "proteins_100g": 6.3,
        "carbohydrates_100g": 57.5,
        "fat_100g": 30.9,
        "sugars_100g": 56.3,
        "saturated-fat_100g": 10.6,
        "fiber_100g": 0,
        "salt_100g": 0.107,
    },
}


class StubOff:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls = 0

    async def product(self, barcode: str):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def use_off(outcome) -> StubOff:
    stub = StubOff(outcome)
    app.dependency_overrides[get_off_client] = lambda: stub
    return stub


@pytest.fixture(autouse=True)
def _clear_override():
    yield
    app.dependency_overrides.pop(get_off_client, None)


def registered(client: TestClient, email: str = "scanner@example.com") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #


def test_a_complete_product_normalises() -> None:
    food = normalise_product(COMPLETE)

    assert food["source"] == "off"
    assert food["source_id"] == "3017620422003"
    assert food["name"] == "Nutella"
    # Only the first brand — "Ferrero,Nutella" is one field with two values.
    assert food["brand"] == "Ferrero"
    assert food["kcal"] == 539


def test_salt_is_converted_to_sodium() -> None:
    """The record carries salt; our schema stores sodium. The factor is a defined
    constant, not an estimate."""
    food = normalise_product(COMPLETE)

    assert food["sodium_mg"] == pytest.approx(0.107 / 2.5 * 1000, rel=1e-3)


def test_kilojoules_are_converted_when_kcal_is_absent() -> None:
    """Older records carry only kJ. 1 kcal = 4.184 kJ exactly."""
    payload = {**COMPLETE, "nutriments": {**COMPLETE["nutriments"]}}
    del payload["nutriments"]["energy-kcal_100g"]
    payload["nutriments"]["energy_100g"] = 2252

    assert normalise_product(payload)["kcal"] == pytest.approx(538.2, rel=1e-3)


def test_a_product_with_no_nutrition_is_refused() -> None:
    """The important one. A confident 0 g of protein on a protein bar is worse
    than telling the user the barcode is not usable."""
    payload = {"code": "123456", "product_name": "Mystery bar", "nutriments": {}}

    with pytest.raises(UnusableProduct) as caught:
        normalise_product(payload)

    # The message names what is missing, so the 422 can explain itself.
    assert "calories" in str(caught.value)


def test_a_missing_optional_nutrient_stays_missing() -> None:
    """Absent fibre stays None and renders as an em dash — never a zero."""
    payload = {**COMPLETE, "nutriments": {**COMPLETE["nutriments"]}}
    del payload["nutriments"]["fiber_100g"]

    assert normalise_product(payload)["fibre_g"] is None


# --------------------------------------------------------------------------- #
# The endpoint
# --------------------------------------------------------------------------- #


def test_a_scan_returns_the_food(client: TestClient) -> None:
    use_off(normalise_product(COMPLETE))
    headers = registered(client)

    response = client.get("/api/v1/foods/barcode/3017620422003", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Nutella"


def test_a_second_scan_is_served_from_the_cache(client: TestClient) -> None:
    """For speed, and to be a good citizen of a free, donation-funded service.

    Not to protect diary history — that was an earlier and incorrect claim.
    `diary_entries` snapshot their nutrients at log time, so an upstream revision
    cannot rewrite what somebody ate, which is exactly what makes `?refresh=true`
    safe to offer."""
    stub = use_off(normalise_product(COMPLETE))
    headers = registered(client, "cached@example.com")

    client.get("/api/v1/foods/barcode/3017620422003", headers=headers)
    client.get("/api/v1/foods/barcode/3017620422003", headers=headers)

    assert stub.calls == 1


def test_an_unknown_barcode_says_what_to_do_next(client: TestClient) -> None:
    use_off(ProductNotFound("0000000000000"))
    headers = registered(client, "unknown@example.com")

    response = client.get("/api/v1/foods/barcode/0000000000000", headers=headers)

    assert response.status_code == 404
    assert "Search for it by name" in response.json()["detail"]


def test_a_product_without_nutrition_is_a_422_not_a_food(client: TestClient) -> None:
    use_off(UnusableProduct("Product 123456 has no calories recorded."))
    headers = registered(client, "empty@example.com")

    response = client.get("/api/v1/foods/barcode/123456", headers=headers)

    assert response.status_code == 422
    assert "nothing to log" in response.json()["detail"]


def test_an_upstream_failure_is_a_502(client: TestClient) -> None:
    use_off(OffUnavailable("connection reset"))
    headers = registered(client, "down@example.com")

    assert client.get("/api/v1/foods/barcode/123456", headers=headers).status_code == 502


def test_a_malformed_barcode_never_reaches_the_network(client: TestClient) -> None:
    stub = use_off(normalise_product(COMPLETE))
    headers = registered(client, "junk@example.com")

    assert client.get("/api/v1/foods/barcode/not-a-barcode", headers=headers).status_code == 422
    assert stub.calls == 0


def test_barcode_lookup_needs_authentication(client: TestClient) -> None:
    use_off(normalise_product(COMPLETE))
    assert client.get("/api/v1/foods/barcode/3017620422003").status_code == 401


# --------------------------------------------------------------------------- #
# Serving size, the sanity check, refresh, and custom foods
# --------------------------------------------------------------------------- #


def test_the_serving_size_becomes_a_portion() -> None:
    """Nobody weighs out 100 g of cereal. The box already says what a serving is."""
    payload = {**COMPLETE, "serving_quantity": 30}

    portions = normalise_product(payload)["portions"]

    assert len(portions) == 1
    assert portions[0]["grams"] == 30
    assert portions[0]["is_default"] is True


def test_an_implausible_serving_size_is_ignored() -> None:
    """Several records store a multipack's net weight here instead of a portion.
    Offering "1 serving (2500 g)" would be worse than offering nothing."""
    payload = {**COMPLETE, "serving_quantity": 2500}

    assert normalise_product(payload)["portions"] == []


def test_a_misplaced_decimal_point_is_refused() -> None:
    """The damaging kind of crowd-sourced error: not a missing field, which is
    obvious, but a plausible number wrong by a factor of ten."""
    payload = {**COMPLETE, "nutriments": {**COMPLETE["nutriments"], "energy-kcal_100g": 5390}}

    with pytest.raises(UnusableProduct) as caught:
        normalise_product(payload)

    assert "mistyped" in str(caught.value)


def test_a_genuinely_zero_calorie_product_is_accepted() -> None:
    """Black coffee and diet drinks have no macros and no calories. The check
    must not read that as a contradiction."""
    payload = {
        "code": "1234567890123",
        "product_name": "Sparkling water",
        "nutriments": {
            "energy-kcal_100g": 0,
            "proteins_100g": 0,
            "carbohydrates_100g": 0,
            "fat_100g": 0,
        },
    }

    assert normalise_product(payload)["kcal"] == 0


def test_a_normal_product_passes_the_check() -> None:
    """The band is wide on purpose — fibre, polyols and label rounding all shift
    the real figure, and this must not reject ordinary food."""
    assert normalise_product(COMPLETE)["kcal"] == 539


def test_refresh_refetches_a_cached_product(client: TestClient) -> None:
    """Safe because diary entries snapshot their nutrients at log time, so an
    upstream revision cannot rewrite what somebody ate."""
    stub = use_off(normalise_product(COMPLETE))
    headers = registered(client, "refresh@example.com")

    client.get("/api/v1/foods/barcode/3017620422003", headers=headers)
    client.get("/api/v1/foods/barcode/3017620422003?refresh=true", headers=headers)

    assert stub.calls == 2


def test_a_custom_food_is_private_to_its_author(client: TestClient) -> None:
    """The difference between this and the catalogue: USDA figures are measured
    and shared, these are one person's reading of one label."""
    mine = registered(client, "author@example.com")

    created = client.post(
        "/api/v1/foods",
        headers=mine,
        json={
            "name": "Zzqxflapjack",
            "kcal": 420,
            "protein_g": 5,
            "carbs_g": 55,
            "fat_g": 20,
            "serving_grams": 60,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source"] == "user"
    assert len(body["portions"]) == 1

    # It does not appear in another user's search.
    #
    # Searched by a nonsense token rather than a real word. An earlier version of
    # this test searched "flapjack", passed, and was wrong: real words also match
    # USDA rows, which crowded the leaked food out of the result list and made a
    # genuine privacy hole look like a passing test.
    theirs = registered(client, "other@example.com")
    results = client.get("/api/v1/foods/search?q=Zzqxflapjack", headers=theirs).json()
    assert results["results"] == []

    # ...but its author still finds it, which is the other half of the rule.
    own = client.get("/api/v1/foods/search?q=Zzqxflapjack", headers=mine).json()
    assert [r["name"] for r in own["results"]] == ["Zzqxflapjack"]


def test_a_custom_food_keeps_a_missing_nutrient_missing(client: TestClient) -> None:
    """A label that does not state fibre must produce null, not zero — the same
    rule every other source follows."""
    headers = registered(client, "nulls@example.com")

    body = client.post(
        "/api/v1/foods",
        headers=headers,
        json={"name": "Mystery bar", "kcal": 200, "protein_g": 5, "carbs_g": 30, "fat_g": 6},
    ).json()

    assert body["fibre_g"] is None


def test_custom_food_barcode_lookup_resolves_approved_or_owned_food(client: TestClient) -> None:
    """Barcode lookup finds a custom/approved food stored in database by source_id barcode."""
    headers = registered(client, "barcode_owner@example.com")
    use_off(UnusableProduct("No nutrition"))

    created = client.post(
        "/api/v1/foods",
        headers=headers,
        json={
            "name": "Barcode Snack",
            "barcode": "6194008555229",
            "kcal": 250,
            "protein_g": 8,
            "carbs_g": 30,
            "fat_g": 10,
        },
    )
    assert created.status_code == 201

    res = client.get("/api/v1/foods/barcode/6194008555229", headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Barcode Snack"

