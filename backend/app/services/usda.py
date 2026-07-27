"""USDA FoodData Central client and normalisation.

**Why the backend proxies this instead of the app calling it directly.**

* **Rate limits.** One API key allows 1,000 requests an hour. A few dozen users
  typing in a search box would exhaust that, and every user would then see
  failures caused by other users.
* **Key secrecy.** Anything shipped in a mobile bundle is public — bundles are
  trivially extracted. A client-side key is a leaked key.
* **Offline and latency.** Cached foods serve instantly from our own Postgres and
  keep working on a bad connection.
* **Shape stability.** USDA's payload is sprawling and inconsistent (see below).
  Normalising once on the server means an upstream change is one backend fix
  rather than a forced app-store release.

**The normalisation rules that matter.** Nutrients arrive in a `foodNutrients`
array keyed by number, not name. Some Foundation foods report only kilojoules.
Branded foods are per *serving*, not per 100 g. Each of those quietly produces a
wrong number if handled naively, and a wrong number here is the one thing this
project refuses to ship.
"""

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.nal.usda.gov/fdc/v1"

#: USDA nutrient numbers. These are stable identifiers; the display names are not.
NUTRIENT_ENERGY_KCAL = "1008"
NUTRIENT_ENERGY_KJ = "1062"
NUTRIENT_ENERGY_ATWATER_GENERAL = "2047"
NUTRIENT_ENERGY_ATWATER_SPECIFIC = "2048"
NUTRIENT_PROTEIN = "1003"
NUTRIENT_FAT = "1004"
NUTRIENT_CARBS = "1005"
NUTRIENT_SUGARS = "2000"
NUTRIENT_FIBRE = "1079"
NUTRIENT_SATURATED_FAT = "1258"
NUTRIENT_SODIUM = "1093"

KJ_PER_KCAL = 4.184

#: Foundation and SR Legacy are curated whole foods; Branded is packaged goods.
DEFAULT_DATA_TYPES = ("Foundation", "SR Legacy", "Branded")


class UsdaUnavailable(RuntimeError):
    """Upstream failed. Distinct from 'no results', which is a normal answer."""


class UnusableFood(ValueError):
    """The payload lacks the nutrients required to track a food honestly.

    Raised rather than filling gaps with zeros. A food we cannot describe
    accurately is one we decline to store — the entire premise of this app is
    that every number is traceable.
    """


def _index_nutrients(payload: dict[str, Any]) -> dict[str, float]:
    """Flatten `foodNutrients` into {identifier: amount}, under every identifier present.

    USDA uses **two different numbering systems**, and which one you get depends
    on the endpoint. This cost real debugging time, so it is worth stating
    plainly:

    * `/food/{id}` nests the modern number: `{"nutrient": {"number": "1008"}}`.
    * `/foods/search` returns `nutrientId: 1008` *and* `nutrientNumber: "203"` —
      where `nutrientNumber` is the **legacy INFOODS tagname**, not the modern
      number. Protein is 203 there and 1003 here.

    Reading `nutrientNumber` alone therefore matches nothing for search results,
    and every food is rejected as having no energy — which looks exactly like
    USDA returning bad data rather than like our bug.

    Indexing under every identifier the entry carries makes lookups by modern
    number work regardless of shape. Legacy numbers are three digits and modern
    ones four, so the two cannot collide.
    """
    indexed: dict[str, float] = {}

    for entry in payload.get("foodNutrients") or []:
        if not isinstance(entry, dict):
            continue

        nested = entry.get("nutrient") or {}
        amount = entry.get("amount") if entry.get("amount") is not None else entry.get("value")
        if amount is None:
            continue

        try:
            value = float(amount)
        except (TypeError, ValueError):
            continue

        for identifier in (
            nested.get("number"),
            nested.get("id"),
            entry.get("nutrientId"),
            entry.get("nutrientNumber"),
            entry.get("number"),
        ):
            if identifier is not None:
                # setdefault: the first shape encountered wins, so a nested
                # modern number is never overwritten by a legacy alias.
                indexed.setdefault(str(identifier), value)

    return indexed


def _resolve_energy(nutrients: dict[str, float]) -> float | None:
    """Find calories, trying every representation USDA uses.

    Some Foundation foods carry no kcal figure at all, only kilojoules or an
    Atwater-calculated value. Falling back through them rescues foods that would
    otherwise be discarded; converting kJ is exact arithmetic, not an estimate.

    Returns None when none exist, and the caller rejects the food. Guessing a
    calorie count is the one thing we will not do.
    """
    for key in (
        NUTRIENT_ENERGY_KCAL,
        NUTRIENT_ENERGY_ATWATER_SPECIFIC,
        NUTRIENT_ENERGY_ATWATER_GENERAL,
    ):
        if key in nutrients:
            return nutrients[key]

    if NUTRIENT_ENERGY_KJ in nutrients:
        return nutrients[NUTRIENT_ENERGY_KJ] / KJ_PER_KCAL

    return None


def _serving_scale_factor(payload: dict[str, Any]) -> float:
    """Multiplier converting a *per-serving* figure to per 100 g.

    Only ever applied to `labelNutrients`. See `_label_nutrients` for why
    `foodNutrients` must NOT be scaled.
    """
    serving_size = payload.get("servingSize")
    unit = (payload.get("servingSizeUnit") or "").lower()

    if not serving_size or unit not in {"g", "ml", "grm", "mlt"}:
        return 0.0
    try:
        size = float(serving_size)
    except (TypeError, ValueError):
        return 0.0

    if size <= 0:
        return 0.0
    return 100.0 / size


#: `labelNutrients` uses its own key names rather than nutrient numbers.
LABEL_KEYS = {
    NUTRIENT_ENERGY_KCAL: "calories",
    NUTRIENT_PROTEIN: "protein",
    NUTRIENT_FAT: "fat",
    NUTRIENT_CARBS: "carbohydrates",
    NUTRIENT_SUGARS: "sugars",
    NUTRIENT_FIBRE: "fiber",
    NUTRIENT_SATURATED_FAT: "saturatedFat",
    NUTRIENT_SODIUM: "sodium",
}


def _label_nutrients(payload: dict[str, Any]) -> dict[str, float]:
    """Per-100 g values derived from a Branded food's nutrition label.

    **The distinction that matters, and that cost real debugging time.**

    `foodNutrients` is per 100 g for *every* data type, Branded included — USDA
    normalises it for us. Scaling it by serving size double-counts: a 32 g
    serving turned an 89 kcal banana into 975 kcal, a number that is obviously
    wrong on sight and would have been quietly wrong in a total.

    `labelNutrients` is the one that is per serving, and it appears only on
    detail responses. So it is the only thing scaled here, and it is used only
    as a fallback when `foodNutrients` lacks what we need.
    """
    label = payload.get("labelNutrients")
    if not isinstance(label, dict):
        return {}

    scale = _serving_scale_factor(payload)
    if scale <= 0:
        # A serving measured in cups cannot be converted without a density.
        # Guessing one would be inventing data.
        return {}

    derived: dict[str, float] = {}
    for number, key in LABEL_KEYS.items():
        entry = label.get(key)
        value = entry.get("value") if isinstance(entry, dict) else None
        if value is None:
            continue
        try:
            derived[number] = float(value) * scale
        except (TypeError, ValueError):
            continue

    return derived


def normalise_food(payload: dict[str, Any]) -> dict[str, Any]:
    """Turn a USDA food into our schema, per 100 g.

    Raises UnusableFood when the required nutrients are absent.
    """
    fdc_id = payload.get("fdcId")
    if fdc_id is None:
        raise UnusableFood("Payload has no fdcId.")

    description = (payload.get("description") or "").strip()
    if not description:
        raise UnusableFood(f"Food {fdc_id} has no description.")

    # `foodNutrients` is per 100 g for every data type and is never scaled.
    # `labelNutrients` fills gaps for Branded foods and *is* scaled, inside
    # _label_nutrients. Values already present win — USDA's own per-100 g figure
    # is more trustworthy than one we derived from a rounded label.
    nutrients = _index_nutrients(payload)
    for number, value in _label_nutrients(payload).items():
        nutrients.setdefault(number, value)

    energy = _resolve_energy(nutrients)
    if energy is None:
        raise UnusableFood(f"Food {fdc_id} reports no energy value in any form.")

    def optional(key: str) -> float | None:
        """None stays None. It means 'the source did not say', not 'zero'."""
        value = nutrients.get(key)
        return round(value, 2) if value is not None else None

    def required(key: str) -> float:
        value = nutrients.get(key)
        if value is None:
            raise UnusableFood(f"Food {fdc_id} is missing nutrient {key}.")
        return round(value, 2)

    return {
        "source": "usda",
        "source_id": str(fdc_id),
        "name": description,
        "brand": (payload.get("brandOwner") or payload.get("brandName") or None),
        "kcal": round(energy, 2),
        "protein_g": required(NUTRIENT_PROTEIN),
        "carbs_g": required(NUTRIENT_CARBS),
        "fat_g": required(NUTRIENT_FAT),
        "sugars_g": optional(NUTRIENT_SUGARS),
        "saturated_fat_g": optional(NUTRIENT_SATURATED_FAT),
        "fibre_g": optional(NUTRIENT_FIBRE),
        "sodium_mg": optional(NUTRIENT_SODIUM),
        "portions": _normalise_portions(payload),
    }


def _normalise_portions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract friendly units with their gram weights.

    Only portions with a real gram weight are kept. A label with no weight
    ("1 serving" of an unspecified size) cannot be turned into a nutrient
    calculation, and offering it would invite the user to log a number we would
    then have to invent.
    """
    portions: list[dict[str, Any]] = []

    for entry in payload.get("foodPortions") or []:
        grams = entry.get("gramWeight")
        if not grams:
            continue

        measure = (entry.get("measureUnit") or {}).get("name") or ""
        modifier = entry.get("modifier") or ""
        amount = entry.get("amount")

        label = " ".join(
            part
            for part in (
                f"{amount:g}" if isinstance(amount, int | float) and amount else "",
                measure if measure not in {"undetermined", ""} else "",
                modifier,
            )
            if part
        ).strip()

        if not label:
            continue
        portions.append({"label": label[:96], "grams": round(float(grams), 2)})

    return portions[:12]


class UsdaClient:
    """Thin async wrapper over the FoodData Central API."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        settings = get_settings()
        params = dict(kwargs.pop("params", {}) or {})
        params["api_key"] = settings.usda_api_key

        client = self._client or httpx.AsyncClient(timeout=15.0)
        try:
            response = await client.request(method, f"{BASE_URL}{path}", params=params, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            # 429 from upstream is worth naming: it means our shared key is
            # exhausted, which is a capacity problem rather than a bad request.
            logger.warning("USDA responded %s for %s", exc.response.status_code, path)
            raise UsdaUnavailable(f"USDA returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            logger.warning("USDA request failed: %s", exc)
            raise UsdaUnavailable("Could not reach USDA FoodData Central") from exc
        finally:
            if self._client is None:
                await client.aclose()

    async def search(self, query: str, *, page_size: int = 25) -> list[dict[str, Any]]:
        payload = await self._request(
            "POST",
            "/foods/search",
            json={
                "query": query,
                "dataType": list(DEFAULT_DATA_TYPES),
                "pageSize": min(page_size, 50),
                # Curated entries before branded ones: someone searching "banana"
                # wants the fruit, not banana-flavoured syrup.
                #
                # Descending, not ascending. The values sort alphabetically as
                # Branded < Foundation < SR Legacy, so ascending puts packaged
                # products first — the exact opposite of what is wanted.
                "sortBy": "dataType.keyword",
                "sortOrder": "desc",
            },
        )
        return payload.get("foods") or []

    async def get_food(self, fdc_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/food/{fdc_id}")
