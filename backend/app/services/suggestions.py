"""Meal suggestions from what the user has actually eaten today.

**No model is involved, and that is a feature.** A suggestion is arithmetic: the
user has some calories and some grams of each macro left, every candidate food
has known values per 100 g, and the question "which of these closes the gap
best" has an answer you can check by hand. Asking a language model to recommend
food would produce something more fluent and less true — and it would put an
unverifiable claim next to numbers the whole app exists to keep verifiable.

The candidate pool is deliberately narrow: foods the user already logs, plus the
short curated list. Suggesting something from the far corners of USDA would be
technically valid and practically useless — nobody wants "Beef, chuck, arm pot
roast, separable lean only" recommended for dinner.
"""

from dataclasses import dataclass

from app.db.models.food import Food

#: A suggestion is only useful if the portion is one a person would eat. These
#: bound the amount we will propose regardless of how well the maths works out:
#: "eat 480 g of peanut butter to hit your fat target" is arithmetically correct
#: and obviously wrong.
MIN_PORTION_G = 30.0
MAX_PORTION_G = 250.0
DEFAULT_PORTION_G = 100.0

#: Calories a single suggestion aims to contribute.
#:
#: A suggestion is a component of a meal, not the meal. Sizing to fill half the
#: remaining budget produced things like "290 g of oats" — arithmetically a fine
#: way to spend 1,100 kcal and not something any person eats. Capping the target
#: keeps portions in the range a plate actually holds, and the ranking still
#: prefers foods that close the macro gap within that portion.
TARGET_PORTION_KCAL = 300.0

#: ...but never more than this share of what is left, so someone with 400 kcal
#: remaining is not handed a 300 kcal suggestion that eats their whole evening.
MAX_SHARE_OF_REMAINING = 0.35

#: Below this many calories left, there is nothing useful to suggest. Telling
#: someone with 40 kcal remaining to eat something is not help.
MIN_REMAINING_KCAL = 120.0


@dataclass(frozen=True)
class Gap:
    """What the user still has room for today."""

    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float

    @property
    def has_room(self) -> bool:
        return self.kcal >= MIN_REMAINING_KCAL

    @property
    def dominant_macro(self) -> str | None:
        """Which macro is furthest behind, in calorie terms.

        Compared as calories rather than grams, because 20 g of fat and 20 g of
        protein are not the same size of gap — 180 kcal against 80. Ranking by
        grams would systematically over-recommend fat.
        """
        shortfalls = {
            "protein": max(0.0, self.protein_g) * 4,
            "carbs": max(0.0, self.carbs_g) * 4,
            "fat": max(0.0, self.fat_g) * 9,
        }
        best = max(shortfalls, key=lambda key: shortfalls[key])
        return best if shortfalls[best] > 0 else None


@dataclass(frozen=True)
class Suggestion:
    food: Food
    grams: float
    kcal: float
    #: Plain-language reason, e.g. "high in protein, and you're 48 g short".
    reason: str


def _portion_for(food: Food, gap: Gap) -> float:
    """How much of this food to propose.

    Sized to the *calorie* gap rather than the macro gap, then clamped to a
    portion a human would recognise. Sizing to the macro gap alone produces
    absurdities — hitting a 50 g protein shortfall from broccoli would mean
    eating nearly two kilos of it.
    """
    kcal_per_gram = float(food.kcal) / 100.0
    if kcal_per_gram <= 0:
        return DEFAULT_PORTION_G

    target_kcal = min(TARGET_PORTION_KCAL, gap.kcal * MAX_SHARE_OF_REMAINING)
    grams = target_kcal / kcal_per_gram
    # Rounded to 5 g. A suggestion of "77 g" implies a precision the estimate
    # does not have, and nobody weighs to the gram from a recommendation.
    return round(min(MAX_PORTION_G, max(MIN_PORTION_G, grams)) / 5) * 5


def _score(food: Food, grams: float, gap: Gap) -> float:
    """How well a portion of this food fits what is missing.

    Higher is better. The scoring rewards closing the dominant shortfall and
    penalises overshooting the calorie budget, which is what keeps it from
    recommending a 700 kcal item to someone with 300 kcal left.
    """
    factor = grams / 100.0
    kcal = float(food.kcal) * factor
    if kcal > gap.kcal:
        return -1.0

    protein = float(food.protein_g) * factor
    carbs = float(food.carbs_g) * factor
    fat = float(food.fat_g) * factor

    contribution = {
        "protein": min(protein, max(0.0, gap.protein_g)) * 4,
        "carbs": min(carbs, max(0.0, gap.carbs_g)) * 4,
        "fat": min(fat, max(0.0, gap.fat_g)) * 9,
    }

    dominant = gap.dominant_macro
    # Double-weight the macro furthest behind. Without this the ranking is just
    # "most calories that fit", which recommends the same energy-dense foods to
    # everyone regardless of what they actually need.
    score = sum(contribution.values())
    if dominant:
        score += contribution[dominant]

    return score


def _reason(food: Food, grams: float, gap: Gap) -> str:
    """Say why this was suggested, in the user's terms.

    A recommendation with no stated reason is indistinguishable from an
    advertisement. Naming the shortfall it addresses is what makes it advice.
    """
    factor = grams / 100.0
    dominant = gap.dominant_macro

    if dominant == "protein" and float(food.protein_g) * factor >= 10:
        short = round(gap.protein_g)
        return f"{round(float(food.protein_g) * factor)} g protein — you're {short} g short today"
    if dominant == "carbs" and float(food.carbs_g) * factor >= 15:
        short = round(gap.carbs_g)
        return f"{round(float(food.carbs_g) * factor)} g carbs — you're {short} g short today"
    if dominant == "fat" and float(food.fat_g) * factor >= 8:
        short = round(gap.fat_g)
        return f"{round(float(food.fat_g) * factor)} g fat — you're {short} g short today"

    return f"Fits your remaining {round(gap.kcal)} kcal"


def suggest(candidates: list[Food], gap: Gap, limit: int = 4) -> list[Suggestion]:
    """Rank candidates against the day's remaining budget.

    Returns an empty list when there is nothing sensible to say — no room left,
    or no candidate that fits. Silence is the right output there; a suggestion
    screen that always shows something eventually shows nonsense.
    """
    if not gap.has_room:
        return []

    scored: list[tuple[float, Suggestion]] = []
    seen: set[str] = set()

    for food in candidates:
        # One suggestion per food name. The cache legitimately holds several
        # near-identical USDA rows for the same thing, and offering three of
        # them looks broken.
        key = food.name.strip().lower()
        if key in seen:
            continue

        grams = _portion_for(food, gap)
        score = _score(food, grams, gap)
        if score <= 0:
            continue

        seen.add(key)
        scored.append(
            (
                score,
                Suggestion(
                    food=food,
                    grams=grams,
                    kcal=round(float(food.kcal) * grams / 100.0, 1),
                    reason=_reason(food, grams, gap),
                ),
            )
        )

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [suggestion for _, suggestion in scored[:limit]]
