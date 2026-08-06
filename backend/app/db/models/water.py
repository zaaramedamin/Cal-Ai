"""Water intake.

**Why a table of drinks and not a counter on the day.**

The screen shows a total, so a single `millilitres_today` column looks like the
obvious design. It is wrong for the same reason the diary is a list of entries:
the user does not think in totals, they think in glasses. Tapping "+250 ml" by
mistake has to be undoable, and undoing a total means subtracting — which cannot
distinguish "remove that tap" from "I actually drank less than I said".

A list also answers questions a counter cannot: when in the day someone drinks,
and whether a low total is one missed glass or a missed afternoon.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import TimestampedCreation, UUIDPrimaryKey


class WaterEntry(UUIDPrimaryKey, TimestampedCreation, Base):
    """One drink."""

    __tablename__ = "water_entries"

    __table_args__ = (
        CheckConstraint("millilitres > 0", name="millilitres_positive"),
        # Bounded deliberately: water intoxication is a real thing, and a typo'd
        # 25000 would otherwise render as a plausible-looking day rather than an
        # obvious mistake.
        CheckConstraint("millilitres <= 5000", name="millilitres_bounded"),
        Index("ix_water_entries_user_date", "user_id", "local_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    #: The user's local calendar day, set server-side from their profile
    #: timezone. Same rule as the diary: a drink at 11pm belongs to that day
    #: whatever UTC thinks.
    local_date: Mapped[date] = mapped_column(Date, nullable=False)

    #: Integer millilitres. Nobody drinks 250.5 ml, and an integer cannot
    #: accumulate rounding error across a day of additions the way a float can.
    millilitres: Mapped[int] = mapped_column(Integer, nullable=False)

    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<WaterEntry {self.millilitres}ml on {self.local_date}>"
