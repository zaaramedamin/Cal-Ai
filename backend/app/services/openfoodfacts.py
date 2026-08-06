"""Open Food Facts: packaged foods, looked up by barcode.

**Why a second source at all.** USDA is authoritative for whole foods and knows
almost nothing about a specific tub of yoghurt in a Carrefour. A barcode is the
one identifier that names *exactly* the product in someone's hand, and Open Food
Facts is the open database that maps them. The two sources answer different
questions, so both are kept and each is labelled with where its numbers came
from.

**The same honesty rule applies.** Open Food Facts is crowd-sourced, so its
records vary from complete to nearly empty. A product missing calories or macros
is refused rather than stored with zeros — `UnusableProduct` below — because a
confident 0 g of protein on a protein bar is worse than telling the user the
barcode is not in the database.
"""

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.tls import use_system_trust_store

logger = logging.getLogger(__name__)

BASE_URL = "https://world.openfoodfacts.org/api/v2"

#: Only the fields we use. Open Food Facts products are large — ingredient
#: lists, images, packaging, ecoscore — and asking for everything wastes their
#: bandwidth and ours on a lookup that needs eight numbers.
FIELDS = ",".join(
    [
        "code",
        "product_name",
        "product_name_en",
        "brands",
        "quantity",
        "serving_quantity",
        "nutriments",
    ]
)

#: Open Food Facts asks every client to identify itself, and rate-limits or bans
#: those that do not. See `off_user_agent` in config.
TIMEOUT_SECONDS = 12.0


class OffUnavailable(RuntimeError):
    """Open Food Facts could not be reached."""


class ProductNotFound(LookupError):
    """The barcode is valid but no product carries it."""


class UnusableProduct(ValueError):
    """The record exists but lacks the nutrients needed to track it honestly.

    Raised rather than filling gaps with zeros. Open Food Facts is
    crowd-sourced: plenty of records are a name and a photograph with no
    nutrition at all, and storing those as a food with 0 kcal would put a
    confident, wrong number into someone's diary.
    """


def _number(nutriments: dict[str, Any], *keys: str) -> float | None:
    """First present numeric value among `keys`.

    Several keys are tried because Open Food Facts stores energy under
    `energy-kcal_100g` on newer records and only `energy_100g` (kilojoules) on
    older ones, and contributors are inconsistent about which they fill.
    """
    for key in keys:
        value = nutriments.get(key)
        if isinstance(value, int | float):
            return float(value)
        # Some records store numbers as strings.
        if isinstance(value, str):
            try:
                return float(value.replace(",", "."))
            except ValueError:
                continue
    return None


#: How far a declared calorie figure may sit from the one its macros imply.
#:
#: Atwater factors — 4 kcal/g for protein and carbohydrate, 9 for fat — reproduce
#: a label to within a few percent for most foods. The band here is deliberately
#: wide, not tight: fibre, polyols and alcohol all shift the real figure, and
#: rounding on the label shifts it again. The purpose is not to audit
#: manufacturers, it is to catch a misplaced decimal point — 5390 kcal typed for
#: 539 — which fails by a factor of ten and cannot be explained by any of that.
ATWATER_MIN_RATIO = 0.5
ATWATER_MAX_RATIO = 2.0

#: Below this the check is skipped. A food with almost no macros — black coffee,
#: a diet drink — has a computed value near zero, where any ratio is meaningless.
ATWATER_FLOOR_KCAL = 20.0


def _atwater_check(kcal: float, protein: float, carbs: float, fat: float, code: str) -> None:
    """Refuse a calorie figure its own macros cannot explain.

    Raises `UnusableProduct`. This is the one validation that catches the most
    damaging kind of crowd-sourced error: not a missing field, which is obvious,
    but a plausible-looking number that is wrong by an order of magnitude.
    """
    implied = 4 * protein + 4 * carbs + 9 * fat

    # Both near zero is a legitimate product, not a contradiction.
    if implied < ATWATER_FLOOR_KCAL and kcal < ATWATER_FLOOR_KCAL:
        return

    # Macros say there is nothing here, but the label claims real calories.
    if implied < ATWATER_FLOOR_KCAL:
        raise UnusableProduct(
            f"Product {code} declares {kcal:.0f} kcal but its macros account for "
            f"almost none of it."
        )

    ratio = kcal / implied
    if ratio < ATWATER_MIN_RATIO or ratio > ATWATER_MAX_RATIO:
        raise UnusableProduct(
            f"Product {code} declares {kcal:.0f} kcal per 100 g, but its protein, "
            f"carbohydrate and fat imply about {implied:.0f}. One of the figures "
            f"is likely mistyped."
        )


def _serving_portion(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The serving size printed on the pack, as a portion.

    Packaged food is eaten in servings, not in hundred-gram units — nobody
    weighs out 100 g of cereal. Open Food Facts carries the figure, so throwing
    it away leaves the user typing grams for something the box already told us.

    Returned empty when absent or implausible, which is the honest outcome: a
    portion is only offered when the label actually stated one.
    """
    grams = _number(payload, "serving_quantity")
    # A serving over a kilo is a parsing artefact — several records store the
    # net weight of a multipack here rather than one portion.
    if grams is None or grams <= 0 or grams > 1000:
        return []

    return [
        {
            "label": f"1 serving ({grams:g} g)",
            "grams": round(grams, 2),
            "is_default": True,
        }
    ]


def normalise_product(payload: dict[str, Any]) -> dict[str, Any]:
    """Turn an Open Food Facts product into our food schema, per 100 g.

    Raises `UnusableProduct` when the required nutrients are absent.
    """
    code = str(payload.get("code") or "").strip()
    if not code:
        raise UnusableProduct("Product has no barcode.")

    name = (payload.get("product_name_en") or payload.get("product_name") or "").strip()
    if not name:
        raise UnusableProduct(f"Product {code} has no name.")

    nutriments = payload.get("nutriments") or {}

    kcal = _number(nutriments, "energy-kcal_100g")
    if kcal is None:
        # Fall back to kilojoules, which older records carry instead. The
        # conversion is exact and defined, not an estimate: 1 kcal = 4.184 kJ.
        kilojoules = _number(nutriments, "energy_100g", "energy-kj_100g")
        if kilojoules is not None:
            kcal = round(kilojoules / 4.184, 2)

    protein = _number(nutriments, "proteins_100g")
    carbs = _number(nutriments, "carbohydrates_100g")
    fat = _number(nutriments, "fat_100g")

    missing = [
        label
        for label, value in (
            ("calories", kcal),
            ("protein", protein),
            ("carbohydrate", carbs),
            ("fat", fat),
        )
        if value is None
    ]
    if missing:
        raise UnusableProduct(
            f"Product {code} ({name}) has no {', '.join(missing)} recorded."
        )

    # Sodium is stored in grams here and in milligrams in our schema. Salt is
    # also often the only figure present, and the conversion between them is a
    # defined constant rather than an estimate.
    sodium_g = _number(nutriments, "sodium_100g")
    if sodium_g is None:
        salt_g = _number(nutriments, "salt_100g")
        sodium_g = salt_g / 2.5 if salt_g is not None else None

    # Checked after the required fields are known present, so the message can
    # name real numbers rather than Nones.
    _atwater_check(kcal, protein, carbs, fat, code)

    brands = (payload.get("brands") or "").split(",")[0].strip() or None

    return {
        "source": "off",
        "source_id": code,
        "name": name,
        "brand": brands,
        # Packaged foods are labelled per 100 g by law in most of the world, and
        # that is what Open Food Facts stores. Nothing needs converting.
        "is_liquid": False,
        "kcal": kcal,
        "protein_g": protein,
        "carbs_g": carbs,
        "fat_g": fat,
        # Optional throughout: absent stays absent, and renders as an em dash
        # rather than becoming a zero somebody might read as measured.
        "sugars_g": _number(nutriments, "sugars_100g"),
        "saturated_fat_g": _number(nutriments, "saturated-fat_100g"),
        "fibre_g": _number(nutriments, "fiber_100g"),
        "sodium_mg": round(sodium_g * 1000, 2) if sodium_g is not None else None,
        "portions": _serving_portion(payload),
    }


class OffClient:
    """Barcode lookups against Open Food Facts."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def product(self, barcode: str) -> dict[str, Any]:
        """Fetch and normalise one product.

        Raises `ProductNotFound`, `UnusableProduct` or `OffUnavailable`.
        """
        settings = get_settings()
        use_system_trust_store()

        client = self._client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
        try:
            response = await client.get(
                f"{BASE_URL}/product/{barcode}.json",
                params={"fields": FIELDS},
                # Open Food Facts bans generic clients. This is not politeness:
                # a default python-httpx agent gets rate-limited quickly.
                headers={"User-Agent": settings.off_user_agent},
            )
        except httpx.HTTPError as exc:
            raise OffUnavailable(str(exc)) from exc
        finally:
            if self._client is None:
                await client.aclose()

        # 404 is their documented "no such product", and it is a normal outcome
        # rather than an error: most barcodes on a shelf are not in the database.
        if response.status_code == 404:
            raise ProductNotFound(barcode)
        if not response.is_success:
            raise OffUnavailable(f"Open Food Facts returned {response.status_code}")

        payload = response.json()
        # They also signal absence with status 0 in a 200 response.
        if payload.get("status") == 0 or not payload.get("product"):
            raise ProductNotFound(barcode)

        return normalise_product(payload["product"])
