"""The curated food catalogue.

**Why this exists next to USDA rather than instead of it.**

USDA is authoritative and unbrowsable. "Chicken" returns forty near-identical
rows written as taxonomy — *Chicken, broilers or fryers, breast, meat only,
cooked, roasted* — and a person who wants to log a chicken breast has to read a
classification scheme to find one. It is the right source of *numbers* and the
wrong source of *names, units and choices*.

So the catalogue is a small, hand-picked menu. USDA still supplies every figure,
but it does so **once, at seed time**, and the verified numbers are stored here
with their `source_id`. Nothing is invented and nothing is looked up while the
user waits.

**Units are the other half of the point.** Storing everything per 100 g is
correct and unusable: nobody weighs milk, and "50 g of egg" is a translation
task the user should never be given. Each food therefore declares how it is
*counted* — grams, millilitres, or whole items — and carries the portions a
person would actually pick from. Grams remain the internal currency, because a
diary has to be summable, but the user never has to think in them.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class UnitKind(StrEnum):
    """How a food is measured when a person talks about it."""

    #: Solids. Portions are gram weights: "1 medium fillet (120 g)".
    GRAMS = "g"
    #: Liquids. Shown in ml and litres; still stored as grams internally, using
    #: the food's own density rather than assuming water.
    MILLILITRES = "ml"
    #: Whole items — eggs, bananas, slices of bread. The user picks a *number*,
    #: and `grams_per_unit` converts it for the diary. This is the case that
    #: makes the whole enum worth having: "2 eggs" is how people think, and
    #: "100 g of egg" is how nobody does.
    COUNT = "unit"


class Portion(BaseModel):
    """One choice offered on the food screen."""

    #: What the user reads: "1 large egg", "1 glass (250 ml)", "1 tbsp".
    label_en: str
    label_fr: str
    #: How many of the food's own unit this portion is — 1 egg, 250 ml, 30 g.
    amount: float = Field(gt=0)
    #: What that weighs. The diary is summed in grams, always.
    grams: float = Field(gt=0)
    is_default: bool = False


class CatalogueFood(BaseModel):
    """A food as the app presents it.

    Names are stored per language rather than translated at render time. A food
    name is not a UI string — "Blanc de poulet" is not a translation of "Chicken
    breast" that a generic dictionary could produce, and getting it wrong in a
    nutrition app is worse than in most places.
    """

    slug: str
    name_en: str
    name_fr: str
    category: str
    emoji: str
    #: Filename of the photo in the catalogue's image store. Null until one is
    #: uploaded; the app renders the emoji in the meantime.
    photo: str | None = None

    unit: UnitKind
    #: For COUNT foods, what one item weighs. Null for grams and millilitres,
    #: where the portion list carries the conversion instead.
    grams_per_unit: float | None = None

    # --- per 100 g, always, whatever the display unit ---------------------
    # Kept per 100 g even for liquids and countables so every number in the
    # database is directly comparable and the diary's arithmetic never has to
    # ask what kind of food it is holding.
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fibre_g: float | None = None
    sugars_g: float | None = None
    saturated_fat_g: float | None = None
    sodium_mg: float | None = None

    #: Where the numbers came from. `usda` plus the FDC id for everything seeded
    #: from FoodData Central — the traceability rule does not relax because the
    #: lookup happened at seed time rather than at request time.
    source: str = "usda"
    source_id: str | None = None

    portions: list[Portion] = Field(default_factory=list)
    #: Sort order within a category, so the list reads deliberately rather than
    #: alphabetically.
    order: int = 0
