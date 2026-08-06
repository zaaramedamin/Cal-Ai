"""Saved meals — a plate the user assembles once and logs in one tap.

**Why this is not `Recipe`.** They look alike: both are a named set of foods with
amounts. They differ in what they are *for*. A recipe divides a total into
servings and is costed per portion, because you cook a pot of chilli and eat a
quarter of it. A meal is eaten as-is — "my breakfast" is three eggs, a glass of
milk and two slices of bread, every time, and dividing it into servings would be
arithmetic the user never asked for.

Merging them would mean a nullable `servings` that changes the meaning of every
other field, which is the shape of a table that later needs splitting again.
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.food import Food
from app.db.models.mixins import TimestampedCreation, UUIDPrimaryKey


class Meal(UUIDPrimaryKey, TimestampedCreation, Base):
    """A named combination, owned by one user.

    Nutrition is not stored, for the same reason it is not stored on a recipe: it
    is a pure function of the items, so a stored copy would go stale the moment
    one changed. It is computed on read, and snapshotted only into the diary
    entries created when the meal is logged — which is the one place an immutable
    record is actually required.
    """

    __tablename__ = "meals"

    # The meals list is always "this user's, by name". Without this it is a
    # sequential scan plus a sort on every load of the meals screen.
    __table_args__ = (Index("ix_meals_user_name", "user_id", "name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    items: Mapped[list["MealItem"]] = relationship(
        back_populates="meal",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MealItem.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Meal {self.name!r}>"


class MealItem(UUIDPrimaryKey, TimestampedCreation, Base):
    """One food in a meal, in the food's own unit."""

    __tablename__ = "meal_items"

    __table_args__ = (
        # A food appears once per meal. Adding the same item twice is a mistake
        # the user cannot see in a list, so it is prevented rather than allowed
        # to silently double a total.
        UniqueConstraint("meal_id", "food_id", name="uq_meal_item"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    meal_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("meals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # RESTRICT rather than SET NULL, matching `recipe_ingredients` and for the
    # same reason: a meal holds no nutrient snapshot, so an item silently
    # vanishing would make it under-report. A diary entry can survive losing its
    # food because it copied the numbers; a meal cannot.
    food_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("foods.id", ondelete="RESTRICT"), nullable=False
    )

    #: In the food's own unit: 2 eggs, 250 ml, 30 g. Converted to grams through
    #: the food's `grams_per_unit` at the moment it is logged.
    amount: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    meal: Mapped[Meal] = relationship(back_populates="items")
    food: Mapped[Food] = relationship()

    def __repr__(self) -> str:
        return f"<MealItem {self.amount} of {self.food_id}>"
