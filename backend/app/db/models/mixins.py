"""Column mixins shared by every table."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKey:
    """A UUID primary key, generated in Python.

    UUIDs rather than auto-incrementing integers, for two reasons that matter to
    this app specifically:

    1. Sequential integer ids leak information. `/users/1` versus `/users/8423`
       tells anyone how many users you have and lets them enumerate accounts.
    2. The id can be generated before the row is inserted, which keeps client
       code simple when we start creating diary entries offline in Phase 6.

    The cost is 16 bytes instead of 4 and slightly worse index locality. At this
    app's scale that is not a real cost.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampedCreation:
    """A creation timestamp, set by the database.

    `server_default=func.now()` means Postgres stamps the row, not Python. That
    matters because the database clock is one clock, while application servers —
    once there is more than one — can disagree with each other by seconds.

    `timezone=True` makes this `timestamptz`. Every timestamp in this schema is
    timezone-aware UTC. The one deliberate exception arrives in Phase 4:
    `diary_entries.local_date` is a plain DATE, because "what day did I eat this"
    is a question about the user's local calendar, not about an instant in time.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
