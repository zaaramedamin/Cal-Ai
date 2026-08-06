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
    #: What **one** of this food's units weighs in grams — one egg, one
    #: millilitre, one gram. Present for every food, not only countables.
    #:
    #: This started as "null except for COUNT, the portions carry the rest" and
    #: was wrong. The portion list only covers the sizes we thought to offer, so
    #: a user typing 300 ml of milk when no 300 ml portion exists left the server
    #: with no way to convert — and the tempting fix, assuming water, is a 3%
    #: error on milk and a 9% one on oil. One number per food, used by every
    #: conversion, means there is nowhere for that assumption to hide.
    grams_per_unit: float = Field(gt=0)

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


class CatalogueSection(BaseModel):
    """One category's worth of foods, ready to render as a section."""

    category: str
    foods: list[CatalogueFood]


class CatalogueResponse(BaseModel):
    """The whole catalogue, in one response.

    Deliberately unpaginated. Thirty-five foods is roughly 20 KB of JSON — less
    than a single photo — and paginating it would mean more code here, more
    state on the client, and a browse screen that stutters as the user scrolls
    through a list short enough to fit in memory twice over. If the catalogue
    ever grows past a few hundred foods this becomes the wrong call, and the
    section shape below is what a `?category=` filter would slot into.

    Both languages travel together rather than the server picking one, so
    switching language in Settings re-renders instantly instead of refetching.
    """

    sections: list[CatalogueSection]
    total: int


class PhotoCredit(BaseModel):
    """Who took one catalogue photograph, and under what terms.

    CC BY and CC BY-SA both require the photographer to be credited wherever the
    image appears. Printing that under every 110pt grid tile would bury the app in
    small print, so the credits are collected onto one screen — which is the
    accepted way to satisfy attribution for a set of images used decoratively.

    Foods photographed for this project have no entry here. Absence means nobody
    is owed credit, not that credit was skipped.
    """

    slug: str
    name_en: str
    #: Photographer, as Wikimedia Commons records them.
    attribution: str
    #: Short licence name, e.g. `CC BY-SA 4.0`.
    license: str
    #: The Commons file page — where the licence can be verified.
    source_url: str | None = None
