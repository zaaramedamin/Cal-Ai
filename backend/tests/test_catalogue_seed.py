"""The curated catalogue and its units.

These test the *unit model*, which is the part that carries real risk. Getting a
density or a gram-per-item wrong produces a number that looks completely
plausible and is quietly wrong by 10-30% on every log of that food, forever.
"""

import pytest

from app.schemas.catalogue import UnitKind
from app.services.catalogue_seed import SEEDS, count, g, ml


def test_every_seed_has_a_unique_slug() -> None:
    """Slugs are the catalogue's primary key and its upsert key."""
    slugs = [seed.slug for seed in SEEDS]

    assert len(slugs) == len(set(slugs))


def test_every_seed_offers_at_least_one_portion() -> None:
    """A food with no portions makes the user type grams, which is the thing
    this whole catalogue exists to avoid."""
    for seed in SEEDS:
        assert seed.portions, f"{seed.slug} has no portions"


def test_exactly_one_default_portion_per_food() -> None:
    """Zero defaults means the screen opens on nothing; two means the choice is
    arbitrary and will differ between renders."""
    for seed in SEEDS:
        defaults = [p for p in seed.portions if p.is_default]
        assert len(defaults) == 1, f"{seed.slug} has {len(defaults)} defaults"


def test_countable_foods_declare_what_one_item_weighs() -> None:
    """The conversion that makes "2 eggs" loggable.

    Without `grams_per_unit` a COUNT food cannot reach the diary, which is summed
    in grams — the food would look fine on screen and fail at the last step.
    """
    for seed in SEEDS:
        if seed.unit is UnitKind.COUNT:
            assert seed.grams_per_unit, f"{seed.slug} is counted but has no grams_per_unit"


def test_bilingual_labels_everywhere() -> None:
    """A missing French label would fall back to English mid-list, which reads
    worse than no translation at all."""
    for seed in SEEDS:
        assert seed.name_en and seed.name_fr
        for portion in seed.portions:
            assert portion.label_en and portion.label_fr, f"{seed.slug} portion missing a label"


# --------------------------------------------------------------------------- #
# The portion builders
# --------------------------------------------------------------------------- #


def test_gram_portions_are_their_own_weight() -> None:
    portion = g("1 fillet", "1 filet", 150)

    assert portion.amount == 150
    assert portion.grams == 150


def test_volume_portions_apply_density_not_water() -> None:
    """The error this prevents is invisible and permanent.

    A millilitre of olive oil weighs 0.91 g. Treating it as 1.0 — the obvious
    default — overstates every spoonful by 10%, on the most calorie-dense food in
    the catalogue, and nothing about the resulting number looks wrong.
    """
    water = ml("1 glass", "1 verre", 250)
    oil = ml("1 tbsp", "1 c. à soupe", 15, 0.91)
    milk = ml("1 glass", "1 verre", 250, 1.03)

    assert water.grams == 250
    assert oil.grams == pytest.approx(13.7, abs=0.05)
    assert milk.grams == pytest.approx(257.5, abs=0.05)
    # The user still picks millilitres; grams are only the storage unit.
    assert oil.amount == 15


def test_count_portions_multiply_out() -> None:
    two_eggs = count("2 eggs", "2 œufs", 2, 50)

    assert two_eggs.amount == 2
    assert two_eggs.grams == 100


def test_fractional_counts_are_supported() -> None:
    """Half an avocado is a real portion; forcing whole items would make the
    catalogue lie about how people eat."""
    half = count("Half an avocado", "Un demi-avocat", 0.5, 150)

    assert half.grams == 75


def test_liquids_are_measured_in_volume() -> None:
    """Milk, juice, oil and coffee must not ask the user for grams."""
    liquids = {"milk", "orange-juice", "olive-oil", "coffee"}

    for seed in SEEDS:
        if seed.slug in liquids:
            assert seed.unit is UnitKind.MILLILITRES, f"{seed.slug} should be measured by volume"
