"""Body stats, goal and weight history."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampedCreation, UUIDPrimaryKey
from app.db.models.user import User


class UserProfile(TimestampedCreation, Base):
    """One row per user. Everything needed to calculate their targets.

    The primary key *is* the user id rather than a separate UUID: this is a
    strict one-to-one, and giving it its own id would make two profiles for one
    user representable in the schema. A shape that cannot express the invalid
    state is better than a constraint that forbids it.
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    sex: Mapped[str] = mapped_column(String(6), nullable=False)

    # Birth date, not age. Age changes on its own, and a stored integer is wrong
    # from the user's next birthday onward — silently, with nothing to notice.
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Numeric, not float. Binary floating point cannot represent 170.1 exactly,
    # and a value that drifts on every read is inexcusable in an app whose whole
    # promise is traceable numbers.
    height_cm: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)

    activity_level: Mapped[str] = mapped_column(String(16), nullable=False)
    goal: Mapped[str] = mapped_column(String(16), nullable=False)

    target_weight_kg: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    # IANA name, e.g. "Europe/Paris". Needed from Phase 4 to decide which day a
    # diary entry belongs to. Stored on the profile rather than derived from the
    # request, because the client is not to be trusted with the date.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return f"<UserProfile user={self.user_id}>"


class WeightEntry(UUIDPrimaryKey, TimestampedCreation, Base):
    """A weighing. A history, never a single mutable field on the profile.

    Weight is the one body stat that genuinely moves, and the trend over weeks is
    the only reading of it that means anything — day to day it swings on water,
    salt and sleep. Storing one current value would throw away exactly the data
    that makes the number useful, and Phase 6's chart could not exist.
    """

    __tablename__ = "weight_entries"

    # One weighing per day per user. Weighing twice replaces the earlier value
    # rather than adding a second point, because two readings on one day tell you
    # about hydration, not progress, and would put a meaningless spike in the
    # trend chart. The cost is that we do not keep both — an acceptable trade for
    # a number whose only useful reading is the trend.
    __table_args__ = (UniqueConstraint("user_id", "recorded_on", name="uq_weight_entry_per_day"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    weight_kg: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    # The user's local calendar day, supplied by the server. Someone weighing
    # themselves at 7am expects it filed under that morning regardless of what
    # UTC thinks.
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return f"<WeightEntry {self.weight_kg}kg on {self.recorded_on}>"
