"""Diary entries — what was eaten, when."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.food import Food
from app.db.models.mixins import TimestampedCreation, UUIDPrimaryKey


class MealSlot(enum.StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class DiaryEntry(UUIDPrimaryKey, TimestampedCreation, Base):
    """One logged food.

    **Why the nutrients are snapshotted here instead of read from `foods`.**

    Recalculating from the food row on every read looks cleaner — one source of
    truth, no duplication. It is wrong, for four reasons:

    1. **History must be immutable.** USDA revises values. If chicken breast is
       restated from 165 to 171 kcal per 100 g, last Tuesday's logged lunch must
       not silently change. A diary is a record of what you ate, not a live query
       against current reference data.
    2. **Recipes mutate.** Swap butter for oil in your "Sunday chilli" and every
       meal ever logged with it would retroactively rewrite itself.
    3. **Rows get deleted.** A user removes a custom food; entries referencing it
       must survive intact rather than becoming holes in their history.
    4. **Performance.** A daily total becomes one SUM over one table, with no
       join through ingredients and foods for every entry.

    The mental model is an **invoice line item**: an invoice stores the price at
    the time of sale. It does not join to the current product price, because what
    it records is a historical fact, not a current one.
    """

    __tablename__ = "diary_entries"

    __table_args__ = (
        # At most one source — never both.
        #
        # This started as "exactly one" and was wrong, in a way a test caught.
        # `food_id` is ON DELETE SET NULL so that deleting a food does not
        # destroy the history of having eaten it. But once it is nulled, an
        # "exactly one" check fires and the delete fails — the two rules
        # contradict each other.
        #
        # "At most one" is the correct rule, because the snapshot is what makes a
        # diary entry meaningful, not the foreign key. An entry whose food has
        # been deleted is still a complete and truthful record of a meal; that is
        # the entire reason the nutrients are copied. Requiring a live reference
        # would make the snapshot pointless.
        #
        # Having *neither* at insert time is prevented in the endpoint, where the
        # food is looked up before the row is built.
        # (Recipes arrive in Phase 5; the column is here now so that migration
        # does not have to rewrite this table.)
        CheckConstraint(
            "NOT (food_id IS NOT NULL AND recipe_id IS NOT NULL)",
            name="at_most_one_source",
        ),
        # The index that matters. Every read is "this user, this day", and
        # without it each diary view is a sequential scan of the whole table.
        Index("ix_diary_entries_user_date", "user_id", "local_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    #: A plain DATE, and the one deliberate exception to timestamptz everywhere.
    #: "What day did I eat this" is a question about the user's local calendar,
    #: not an instant in time. Computed server-side from the profile's timezone —
    #: the client says which day it wants to *read*, never which day to write.
    local_date: Mapped[date] = mapped_column(Date, nullable=False)

    meal_slot: Mapped[str] = mapped_column(String(16), nullable=False)

    # SET NULL rather than CASCADE: deleting a food must not delete the history
    # of having eaten it. The snapshot below keeps the entry meaningful.
    food_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("foods.id", ondelete="SET NULL"), nullable=True
    )
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    quantity_grams: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)

    #: Copied at log time so the row survives the food changing or vanishing.
    food_name: Mapped[str] = mapped_column(String(255), nullable=False)
    food_brand: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    # --- the snapshot: totals for this quantity, not per 100 g -------------
    kcal: Mapped[float] = mapped_column(Numeric(9, 2), nullable=False)
    protein_g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    carbs_g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    fat_g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)

    # Still nullable, and still meaning "the source never said". Summing a day's
    # fibre has to be able to report that the total is partial.
    sugars_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True, default=None)
    saturated_fat_g: Mapped[float | None] = mapped_column(
        Numeric(8, 2), nullable=True, default=None
    )
    fibre_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True, default=None)
    sodium_mg: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True, default=None)

    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    food: Mapped[Food | None] = relationship()

    def __repr__(self) -> str:
        return f"<DiaryEntry {self.food_name!r} {self.quantity_grams}g on {self.local_date}>"
