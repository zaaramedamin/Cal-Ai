"""Foods and their friendly portions.

Every row here is traceable. `source` and `source_id` are not decoration — they
are what lets any number in the app be followed back to USDA or Open Food Facts.
A food we cannot attribute is a food we should not be storing.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampedCreation, UUIDPrimaryKey


class FoodSource(enum.StrEnum):
    USDA = "usda"
    OFF = "off"
    #: Created by a user. Still never invented by us — the user asserts it.
    USER = "user"
    #: The one source whose numbers are not measured.
    #:
    #: Written only when a photo scan identifies a food that neither USDA nor the
    #: cache can match, and only ever surfaced with a visible warning. It is
    #: excluded from ordinary food search, so a row like this can never reach a
    #: user who did not watch it being estimated. Everything else in this table
    #: is traceable to a measurement; this is traceable to a guess, and the app
    #: has to keep saying so.
    AI_ESTIMATE = "ai_estimate"


class Food(UUIDPrimaryKey, TimestampedCreation, Base):
    """A food, normalised to per 100 g (or per 100 ml for liquids).

    **Why nullable nutrients matter more than they look.**

    `kcal`, `protein_g`, `carbs_g` and `fat_g` are NOT NULL: a food without them
    is useless for tracking and we reject it at import rather than store a hole.

    `sugars_g`, `saturated_fat_g`, `fibre_g` and `sodium_mg` are nullable,
    because USDA Foundation entries genuinely omit them. This is the schema-level
    enforcement of "never invent a nutrition value": if the source does not
    report fibre, the column is NULL and the app renders an em dash, not `0 g`.

    Defaulting those to zero would be inventing data — and worse, it would be
    invisible. A user would see a confident `0 g fibre` for wholemeal bread and
    have no way to know the number was fabricated by our import script.
    """

    __tablename__ = "foods"

    # One row per upstream item. The unique constraint is what makes the cache a
    # cache rather than a pile of duplicates: re-importing updates in place.
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_food_source_id"),)

    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    #: Drives whether portions read as grams or millilitres. Both are stored as
    #: grams internally; this only changes the label.
    is_liquid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- per 100 g / 100 ml, always -------------------------------------
    # Numeric rather than float throughout. These are the numbers the whole app
    # exists to report, and binary floating point cannot represent 0.1 exactly.
    kcal: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    protein_g: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    carbs_g: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    fat_g: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)

    sugars_g: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True, default=None)
    saturated_fat_g: Mapped[float | None] = mapped_column(
        Numeric(7, 2), nullable=True, default=None
    )
    fibre_g: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True, default=None)
    sodium_mg: Mapped[float | None] = mapped_column(Numeric(9, 2), nullable=True, default=None)

    #: When we last pulled this from upstream. Phase 6 uses it to refresh stale
    #: rows; for now it makes "how old is this number" answerable.
    data_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    #: Who created it, for user-authored foods. Null for USDA and Open Food Facts.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )

    portions: Mapped[list["FoodPortion"]] = relationship(
        back_populates="food", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Food {self.name!r} ({self.source}:{self.source_id})>"


class FoodPortion(UUIDPrimaryKey, TimestampedCreation, Base):
    """A friendly unit mapped to a gram weight.

    Portions are a separate table rather than columns on `foods` because a food
    has many of them — "1 medium banana", "1 cup sliced", "1 small" — and the set
    differs per food. Storing them inline would mean a fixed number of slots and
    a schema change to add one.

    Everything is grams underneath. The label is presentation; the gram weight is
    the fact. That is what keeps a diary entry comparable across foods logged in
    completely different units.
    """

    __tablename__ = "food_portions"

    food_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("foods.id", ondelete="CASCADE"), nullable=False, index=True
    )

    label: Mapped[str] = mapped_column(String(96), nullable=False)
    grams: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)

    #: The portion offered first. Falls back to 100 g when nothing is marked.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    food: Mapped[Food] = relationship(back_populates="portions")

    def __repr__(self) -> str:
        return f"<FoodPortion {self.label!r} = {self.grams}g>"
