"""User-created recipes."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.food import Food
from app.db.models.mixins import TimestampedCreation, UUIDPrimaryKey


class Recipe(UUIDPrimaryKey, TimestampedCreation, Base):
    """A meal assembled from foods, divided into servings.

    Nutrition is **not stored here**. It is a pure function of the ingredients
    and the serving count, so a stored copy would go stale the moment an
    ingredient changed — the same reasoning as calorie targets. It is computed on
    read and snapshotted only at the point a diary entry is created, which is
    where an immutable record is actually required.
    """

    __tablename__ = "recipes"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # How many portions the whole recipe makes. Integer rather than decimal: "I
    # made 4 portions" is how people think, and 2.5 servings invites the user to
    # do arithmetic the app should be doing.
    servings: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    #: Groundwork for sharing. Nothing reads it yet, and no endpoint exposes
    #: another user's recipes — a flag with no enforcement behind it would be a
    #: false promise, so authorisation stays "owner only" until sharing is real.
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RecipeIngredient.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Recipe {self.name!r} ({self.servings} servings)>"


class RecipeIngredient(UUIDPrimaryKey, TimestampedCreation, Base):
    """One food in a recipe, in grams."""

    __tablename__ = "recipe_ingredients"

    # A food appears once per recipe. Adding the same ingredient twice is a
    # mistake the user cannot see in a list, so it is prevented rather than
    # allowed to silently double a total.
    __table_args__ = (
        UniqueConstraint("recipe_id", "food_id", name="uq_recipe_ingredient"),
    )

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # RESTRICT, not SET NULL. A recipe with a missing ingredient cannot be
    # costed at all — unlike a diary entry, which keeps its snapshot and stays
    # meaningful. Refusing the delete is better than leaving a recipe that
    # silently under-reports.
    food_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("foods.id", ondelete="RESTRICT"), nullable=False
    )

    grams: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)

    #: Preserves the order the cook added things in, which usually mirrors the
    #: order they are used. Sorting alphabetically would scramble a method.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    food: Mapped[Food] = relationship()

    def __repr__(self) -> str:
        return f"<RecipeIngredient {self.grams}g of {self.food_id}>"
