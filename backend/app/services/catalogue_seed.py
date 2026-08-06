"""The curated catalogue, and the script that fills in its numbers from USDA.

Each entry here declares what a food *is* — its names, how it is counted, the
portions a person would pick. It declares no nutrition at all. The numbers are
fetched from USDA FoodData Central by `seed_catalogue`, stored alongside the FDC
id that produced them, and never looked up again at request time.

That split is the whole design. Curation decides what the user sees; USDA decides
what the numbers are; neither gets to do the other's job.
"""

import logging
from datetime import UTC, datetime
from typing import Any, NamedTuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.food import Food, FoodKind, FoodPortion
from app.schemas.catalogue import CatalogueFood, Portion, UnitKind
from app.services.usda import UnusableFood, UsdaClient, UsdaUnavailable, normalise_food

logger = logging.getLogger(__name__)


class Seed(NamedTuple):
    slug: str
    name_en: str
    name_fr: str
    category: str
    emoji: str
    unit: UnitKind
    #: Searched against USDA to find the row whose numbers this food adopts.
    query: str
    #: What one of this food's units weighs. One item for COUNT, one millilitre
    #: (i.e. the density) for MILLILITRES. Left null for GRAMS, where it is 1 by
    #: definition and writing it out on twenty entries would be noise.
    #:
    #: For liquids this must agree with the density passed to `ml()` below;
    #: `test_catalogue_seed` asserts it on every portion, because a density that
    #: drifts out of step with its portions produces numbers that look entirely
    #: reasonable and are quietly wrong on every log of that food.
    grams_per_unit: float | None = None
    portions: tuple[Portion, ...] = ()

    @property
    def resolved_grams_per_unit(self) -> float:
        return 1.0 if self.grams_per_unit is None else self.grams_per_unit


def g(label_en: str, label_fr: str, grams: float, *, default: bool = False) -> Portion:
    """A gram portion — `amount` and `grams` are the same number."""
    return Portion(
        label_en=label_en, label_fr=label_fr, amount=grams, grams=grams, is_default=default
    )


def ml(
    label_en: str, label_fr: str, millilitres: float, density: float = 1.0, *, default: bool = False
) -> Portion:
    """A volume portion.

    `density` is grams per millilitre and defaults to water. Milk is 1.03, oil is
    0.91 — assuming 1.0 for oil would overstate a tablespoon by nearly 10%, which
    is the kind of quiet error this whole codebase exists to avoid.
    """
    return Portion(
        label_en=label_en,
        label_fr=label_fr,
        amount=millilitres,
        grams=round(millilitres * density, 1),
        is_default=default,
    )


def count(
    label_en: str, label_fr: str, items: float, grams_each: float, *, default: bool = False
) -> Portion:
    """A whole-item portion: "2 eggs", "1 slice"."""
    return Portion(
        label_en=label_en,
        label_fr=label_fr,
        amount=items,
        grams=round(items * grams_each, 1),
        is_default=default,
    )


# --------------------------------------------------------------------------- #
# The catalogue.
#
# Gram weights below are conventional serving sizes, not nutrition claims — they
# say how big a medium egg is, not what is in it. Every nutrient comes from USDA.
# --------------------------------------------------------------------------- #

SEEDS: tuple[Seed, ...] = (
    # --- Protein ---------------------------------------------------------
    Seed(
        "chicken-breast",
        "Chicken breast",
        "Blanc de poulet",
        "Protein",
        "🍗",
        UnitKind.GRAMS,
        "chicken breast roasted",
        portions=(
            g("1 small fillet", "1 petit filet", 100),
            g("1 fillet", "1 filet", 150, default=True),
            g("1 large fillet", "1 grand filet", 200),
        ),
    ),
    Seed(
        "egg",
        "Egg",
        "Œuf",
        "Protein",
        "🥚",
        UnitKind.COUNT,
        "egg whole raw fresh",
        grams_per_unit=50,
        portions=(
            count("1 egg", "1 œuf", 1, 50),
            count("2 eggs", "2 œufs", 2, 50, default=True),
            count("3 eggs", "3 œufs", 3, 50),
        ),
    ),
    Seed(
        "salmon",
        "Salmon",
        "Saumon",
        "Protein",
        "🐟",
        UnitKind.GRAMS,
        "salmon atlantic cooked",
        portions=(
            g("1 fillet", "1 pavé", 130, default=True),
            g("1 large fillet", "1 grand pavé", 180),
        ),
    ),
    Seed(
        "tuna-canned",
        "Tuna, canned",
        "Thon en boîte",
        "Protein",
        "🐠",
        UnitKind.GRAMS,
        "tuna light canned in water",
        portions=(g("1 small tin", "1 petite boîte", 80, default=True), g("1 tin", "1 boîte", 145)),
    ),
    Seed(
        "beef-mince",
        "Beef mince",
        "Bœuf haché",
        "Protein",
        "🥩",
        UnitKind.GRAMS,
        "ground beef cooked",
        portions=(
            g("1 portion", "1 portion", 125, default=True),
            g("1 large portion", "1 grande portion", 200),
        ),
    ),
    Seed(
        "tofu",
        "Tofu",
        "Tofu",
        "Protein",
        "🧊",
        UnitKind.GRAMS,
        "tofu firm prepared",
        portions=(g("1 portion", "1 portion", 100, default=True), g("1 block", "1 bloc", 250)),
    ),
    Seed(
        "lentils",
        "Lentils, cooked",
        "Lentilles cuites",
        "Protein",
        "🫘",
        UnitKind.GRAMS,
        "lentils cooked boiled",
        portions=(g("1 serving", "1 portion", 100, default=True), g("1 bowl", "1 bol", 200)),
    ),
    Seed(
        "chickpeas",
        "Chickpeas",
        "Pois chiches",
        "Protein",
        "🫛",
        UnitKind.GRAMS,
        "chickpeas cooked",
        portions=(g("1 serving", "1 portion", 100, default=True), g("1 tin", "1 boîte", 240)),
    ),
    # --- Carbs -----------------------------------------------------------
    Seed(
        "rice-white",
        "White rice, cooked",
        "Riz blanc cuit",
        "Carbs",
        "🍚",
        UnitKind.GRAMS,
        "rice white cooked",
        portions=(
            g("1 serving", "1 portion", 150, default=True),
            g("1 large bowl", "1 grand bol", 250),
        ),
    ),
    Seed(
        "pasta",
        "Pasta, cooked",
        "Pâtes cuites",
        "Carbs",
        "🍝",
        UnitKind.GRAMS,
        "pasta cooked enriched",
        portions=(
            g("1 serving", "1 portion", 180, default=True),
            g("1 large bowl", "1 grand bol", 280),
        ),
    ),
    Seed(
        "bread",
        "Bread",
        "Pain",
        "Carbs",
        "🍞",
        UnitKind.COUNT,
        "bread whole wheat",
        grams_per_unit=32,
        portions=(
            count("1 slice", "1 tranche", 1, 32),
            count("2 slices", "2 tranches", 2, 32, default=True),
        ),
    ),
    Seed(
        "oats",
        "Oats",
        "Flocons d'avoine",
        "Carbs",
        "🥣",
        UnitKind.GRAMS,
        "oats rolled dry",
        portions=(
            g("1 serving", "1 portion", 40),
            g("1 large serving", "1 grande portion", 60, default=True),
        ),
    ),
    Seed(
        "potato",
        "Potato",
        "Pomme de terre",
        "Carbs",
        "🥔",
        UnitKind.COUNT,
        "potato baked flesh and skin",
        grams_per_unit=170,
        portions=(
            count("1 potato", "1 pomme de terre", 1, 170, default=True),
            count("2 potatoes", "2 pommes de terre", 2, 170),
        ),
    ),
    Seed(
        "sweet-potato",
        "Sweet potato",
        "Patate douce",
        "Carbs",
        "🍠",
        UnitKind.COUNT,
        "sweet potato cooked baked",
        grams_per_unit=150,
        portions=(count("1 sweet potato", "1 patate douce", 1, 150, default=True),),
    ),
    # --- Fruit -----------------------------------------------------------
    Seed(
        "banana",
        "Banana",
        "Banane",
        "Fruit",
        "🍌",
        UnitKind.COUNT,
        "bananas raw",
        grams_per_unit=118,
        portions=(
            count("1 banana", "1 banane", 1, 118, default=True),
            count("2 bananas", "2 bananes", 2, 118),
        ),
    ),
    Seed(
        "apple",
        "Apple",
        "Pomme",
        "Fruit",
        "🍎",
        UnitKind.COUNT,
        "apples raw with skin",
        grams_per_unit=182,
        portions=(count("1 apple", "1 pomme", 1, 182, default=True),),
    ),
    Seed(
        "orange",
        "Orange",
        "Orange",
        "Fruit",
        "🍊",
        UnitKind.COUNT,
        "oranges raw navels",
        grams_per_unit=140,
        portions=(count("1 orange", "1 orange", 1, 140, default=True),),
    ),
    Seed(
        "strawberries",
        "Strawberries",
        "Fraises",
        "Fruit",
        "🍓",
        UnitKind.GRAMS,
        "strawberries raw",
        portions=(g("1 handful", "1 poignée", 80), g("1 bowl", "1 bol", 150, default=True)),
    ),
    Seed(
        "blueberries",
        "Blueberries",
        "Myrtilles",
        "Fruit",
        "🫐",
        UnitKind.GRAMS,
        "blueberries raw",
        portions=(g("1 handful", "1 poignée", 75, default=True), g("1 bowl", "1 bol", 140)),
    ),
    Seed(
        "avocado",
        "Avocado",
        "Avocat",
        "Fruit",
        "🥑",
        UnitKind.COUNT,
        "avocados raw",
        grams_per_unit=150,
        portions=(
            count("Half an avocado", "Un demi-avocat", 0.5, 150, default=True),
            count("1 avocado", "1 avocat", 1, 150),
        ),
    ),
    # --- Vegetables ------------------------------------------------------
    Seed(
        "broccoli",
        "Broccoli",
        "Brocoli",
        "Vegetables",
        "🥦",
        UnitKind.GRAMS,
        "broccoli cooked boiled",
        portions=(
            g("1 serving", "1 portion", 90, default=True),
            g("1 large serving", "1 grande portion", 150),
        ),
    ),
    Seed(
        "tomato",
        "Tomato",
        "Tomate",
        "Vegetables",
        "🍅",
        UnitKind.COUNT,
        "tomatoes red ripe raw",
        grams_per_unit=123,
        portions=(count("1 tomato", "1 tomate", 1, 123, default=True),),
    ),
    Seed(
        "carrot",
        "Carrot",
        "Carotte",
        "Vegetables",
        "🥕",
        UnitKind.COUNT,
        "carrots raw",
        grams_per_unit=61,
        portions=(
            count("1 carrot", "1 carotte", 1, 61, default=True),
            count("2 carrots", "2 carottes", 2, 61),
        ),
    ),
    Seed(
        "spinach",
        "Spinach",
        "Épinards",
        "Vegetables",
        "🥬",
        UnitKind.GRAMS,
        "spinach raw",
        portions=(g("1 handful", "1 poignée", 30, default=True), g("1 bag", "1 sachet", 100)),
    ),
    Seed(
        "bell-pepper",
        "Bell pepper",
        "Poivron",
        "Vegetables",
        "🫑",
        UnitKind.COUNT,
        "peppers sweet red raw",
        grams_per_unit=119,
        portions=(count("1 pepper", "1 poivron", 1, 119, default=True),),
    ),
    Seed(
        "cucumber",
        "Cucumber",
        "Concombre",
        "Vegetables",
        "🥒",
        UnitKind.GRAMS,
        "cucumber with peel raw",
        portions=(
            g("A few slices", "Quelques rondelles", 50),
            g("Half a cucumber", "Un demi-concombre", 150, default=True),
        ),
    ),
    # --- Dairy and liquids ----------------------------------------------
    Seed(
        "milk",
        "Milk",
        "Lait",
        "Dairy",
        "🥛",
        UnitKind.MILLILITRES,
        "milk whole 3.25% milkfat",
        grams_per_unit=1.03,
        portions=(
            ml("1 glass", "1 verre", 250, 1.03, default=True),
            ml("1 large glass", "1 grand verre", 350, 1.03),
            ml("1 litre", "1 litre", 1000, 1.03),
        ),
    ),
    Seed(
        "greek-yoghurt",
        "Greek yoghurt",
        "Yaourt grec",
        "Dairy",
        "🍶",
        UnitKind.GRAMS,
        "yogurt greek plain nonfat",
        portions=(g("1 pot", "1 pot", 150, default=True), g("1 large pot", "1 grand pot", 200)),
    ),
    Seed(
        "cheddar",
        "Cheddar",
        "Cheddar",
        "Dairy",
        "🧀",
        UnitKind.GRAMS,
        "cheese cheddar",
        portions=(g("1 slice", "1 tranche", 25, default=True), g("1 portion", "1 portion", 50)),
    ),
    Seed(
        "butter",
        "Butter",
        "Beurre",
        "Dairy",
        "🧈",
        UnitKind.GRAMS,
        "butter salted",
        portions=(g("1 tsp", "1 c. à café", 5, default=True), g("1 tbsp", "1 c. à soupe", 14)),
    ),
    Seed(
        "orange-juice",
        "Orange juice",
        "Jus d'orange",
        "Drinks",
        "🧃",
        UnitKind.MILLILITRES,
        "orange juice raw",
        grams_per_unit=1.04,
        portions=(
            ml("1 glass", "1 verre", 250, 1.04, default=True),
            ml("1 litre", "1 litre", 1000, 1.04),
        ),
    ),
    Seed(
        "coffee",
        "Coffee",
        "Café",
        "Drinks",
        "☕",
        UnitKind.MILLILITRES,
        "coffee brewed prepared with tap water",
        portions=(ml("1 cup", "1 tasse", 240, default=True), ml("1 mug", "1 mug", 350)),
    ),
    # --- Fats and extras -------------------------------------------------
    Seed(
        "olive-oil",
        "Olive oil",
        "Huile d'olive",
        "Fats",
        "🫒",
        UnitKind.MILLILITRES,
        "oil olive salad or cooking",
        grams_per_unit=0.91,
        portions=(
            ml("1 tsp", "1 c. à café", 5, 0.91, default=True),
            ml("1 tbsp", "1 c. à soupe", 15, 0.91),
        ),
    ),
    Seed(
        "peanut-butter",
        "Peanut butter",
        "Beurre de cacahuète",
        "Fats",
        "🥜",
        UnitKind.GRAMS,
        "peanut butter smooth",
        portions=(g("1 tbsp", "1 c. à soupe", 16, default=True), g("2 tbsp", "2 c. à soupe", 32)),
    ),
    Seed(
        "almonds",
        "Almonds",
        "Amandes",
        "Fats",
        "🌰",
        UnitKind.GRAMS,
        "nuts almonds",
        portions=(
            g("1 handful", "1 poignée", 28, default=True),
            g("1 large handful", "1 grande poignée", 45),
        ),
    ),
)


async def seed_catalogue(
    session: AsyncSession, client: UsdaClient | None = None, *, force: bool = False
) -> dict[str, Any]:
    """Fill in each catalogue entry's numbers from USDA.

    **Resumable on purpose.** Already-seeded foods are skipped unless `force`, so
    running this repeatedly under a rate-limited key fills the catalogue in
    batches rather than failing whole. That matters here: the shared DEMO_KEY
    allows 30 requests an hour, and this list is longer than that.

    Returns a tally so a caller can see what happened rather than guessing from
    the logs.
    """
    usda = client or UsdaClient()
    tally: dict[str, Any] = {"seeded": 0, "skipped": 0, "failed": 0}

    for index, seed in enumerate(SEEDS):
        existing = (
            await session.execute(select(Food).where(Food.slug == seed.slug))
        ).scalar_one_or_none()
        if existing is not None and not force:
            tally["skipped"] += 1
            continue

        try:
            payloads = await usda.search(seed.query, page_size=3)
        except UsdaUnavailable as exc:
            # Stop rather than burning the rest of the list on calls that will
            # fail the same way.
            #
            # The reason is carried back to the caller rather than left to the
            # logs. It used to be guessed at — the CLI printed "nearly always the
            # rate limit" — and that guess was wrong the first time it mattered:
            # the real cause was a TLS certificate that could not be verified,
            # and the advice sent us looking at API quotas instead.
            logger.warning("USDA unavailable at %r, stopping: %s", seed.slug, exc)
            tally["stopped_because"] = str(exc)  # type: ignore[assignment]
            break

        normalised = None
        for payload in payloads:
            try:
                normalised = normalise_food(payload)
                break
            except UnusableFood:
                # Rows missing the core nutrients are routine; try the next hit.
                continue

        if normalised is None:
            logger.warning("No usable USDA row for %r (%s)", seed.slug, seed.query)
            tally["failed"] += 1
            continue

        food = CatalogueFood(
            slug=seed.slug,
            name_en=seed.name_en,
            name_fr=seed.name_fr,
            category=seed.category,
            emoji=seed.emoji,
            unit=seed.unit,
            grams_per_unit=seed.resolved_grams_per_unit,
            kcal=normalised["kcal"],
            protein_g=normalised["protein_g"],
            carbs_g=normalised["carbs_g"],
            fat_g=normalised["fat_g"],
            fibre_g=normalised.get("fibre_g"),
            sugars_g=normalised.get("sugars_g"),
            saturated_fat_g=normalised.get("saturated_fat_g"),
            sodium_mg=normalised.get("sodium_mg"),
            source="usda",
            source_id=str(normalised["source_id"]),
            portions=list(seed.portions),
            order=index,
        )

        await _upsert_catalogue_food(session, existing, food)
        tally["seeded"] += 1
        logger.info("Seeded %s from USDA %s", seed.slug, food.source_id)

    return tally


async def _upsert_catalogue_food(
    session: AsyncSession, existing: Food | None, food: CatalogueFood
) -> Food:
    """Write one catalogue food and replace its portions.

    Portions are deleted and rewritten rather than merged. They are a small,
    wholly-derived list, and a merge would have to decide what a "changed" portion
    is — by label, which the curator may have reworded, or by grams, which is the
    thing most likely to be corrected. Replacing sidesteps a question with no good
    answer for a list of at most four rows.

    **Converges on an existing cached row.** If an ordinary search already pulled
    this FDC id into `foods`, that row is promoted to `catalogue` rather than a
    second one being inserted. Two reasons: `uq_food_source_id` would reject the
    duplicate anyway, and more importantly a catalogue food *is* a USDA food —
    logging "1 verre de lait" and searching "milk" should land on one row, so any
    diary entry already pointing at the cached row keeps working and gains the
    curated name.
    """
    if existing is None:
        existing = (
            await session.execute(
                select(Food).where(
                    Food.source == food.source, Food.source_id == food.source_id
                )
            )
        ).scalar_one_or_none()

    row = existing or Food(source=food.source, source_id=food.source_id)

    row.kind = FoodKind.CATALOGUE
    row.slug = food.slug
    row.source = food.source
    row.source_id = food.source_id
    row.name = food.name_en
    row.name_fr = food.name_fr
    row.category = food.category
    row.emoji = food.emoji
    row.sort_order = food.order
    row.unit = food.unit.value
    row.grams_per_unit = food.grams_per_unit
    row.is_liquid = food.unit is UnitKind.MILLILITRES
    row.kcal = food.kcal
    row.protein_g = food.protein_g
    row.carbs_g = food.carbs_g
    row.fat_g = food.fat_g
    row.fibre_g = food.fibre_g
    row.sugars_g = food.sugars_g
    row.saturated_fat_g = food.saturated_fat_g
    row.sodium_mg = food.sodium_mg
    row.data_fetched_at = datetime.now(UTC)

    if existing is None:
        session.add(row)
    await session.flush()

    await session.execute(delete(FoodPortion).where(FoodPortion.food_id == row.id))
    for portion in food.portions:
        session.add(
            FoodPortion(
                food_id=row.id,
                label=portion.label_en,
                label_fr=portion.label_fr,
                amount=portion.amount,
                grams=portion.grams,
                is_default=portion.is_default,
            )
        )

    await session.commit()
    return row
