"""User accounts and refresh token sessions."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampedCreation, UUIDPrimaryKey


class User(UUIDPrimaryKey, TimestampedCreation, Base):
    __tablename__ = "users"

    # CITEXT — a case-insensitive text type — rather than plain text.
    #
    # Email addresses are case-insensitive in practice, so Alice@x.com and
    # alice@x.com are one person and must not be able to register twice. We could
    # instead lowercase in Python before every read and write, but that only
    # holds until one code path forgets, and the bug it produces is a duplicate
    # account that is very unpleasant to untangle after the fact.
    #
    # Making it a property of the column means the database enforces it, and no
    # future query can opt out. The unique constraint below then means what a
    # person would assume it means.
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False, index=True)

    # Length 255 is generous: an argon2id hash is ~100 characters, but the format
    # embeds its parameters, so raising the cost settings later lengthens it.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        # Deliberately excludes email and password_hash. Repr output ends up in
        # logs and exception traces, which are exactly the places personal data
        # should not appear.
        return f"<User {self.id}>"


class RevocationReason(enum.StrEnum):
    """Why a refresh token stopped being valid.

    This is not bookkeeping — the distinction changes behaviour, and getting it
    wrong produces a genuinely bad bug.

    A token revoked by ROTATED was spent by a legitimate refresh. If that same
    token is presented again, two parties hold it and one of them is a thief, so
    the safe response is to revoke every session for the user.

    A token revoked by LOGOUT was ended deliberately. A client replaying it is
    overwhelmingly likely to be a stale app that has not noticed it was signed
    out. Treating that as theft would sign the user out of every other device
    every time an old phone retried in the background.

    Same `revoked_at`, completely different correct response.
    """

    ROTATED = "rotated"
    LOGOUT = "logout"
    LOGOUT_ALL = "logout_all"
    REUSE_DETECTED = "reuse_detected"


class RefreshToken(UUIDPrimaryKey, TimestampedCreation, Base):
    """One long-lived session.

    A row here *is* a logged-in device. Deleting or revoking it logs that device
    out, which is the capability an access token alone cannot give us: a JWT is
    valid until it expires and there is no way to recall it.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        # ondelete CASCADE at the database level, not just in the ORM. If a user
        # is ever deleted by a migration or by hand in psql, their sessions must
        # go too — orphaned credential rows are the kind of thing that quietly
        # survives a GDPR deletion request.
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The SHA-256 of the token, never the token. Always 64 hex characters.
    # Unique so that a token can be looked up directly, and so a duplicate is
    # impossible even in a race.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Set on logout, and on rotation when the token is exchanged for a new one.
    # We keep the row rather than deleting it: a *used* token being presented
    # again is the signature of a stolen token, and we can only detect that if
    # the spent row still exists to be recognised. See `revoke_all_for_user`.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Stored as text rather than a Postgres ENUM type. Postgres enums require a
    # migration to add a value and cannot drop one at all, which is a lot of
    # friction for a field we will want to extend (password change, admin
    # revocation). A CHECK constraint gives the same guarantee and is alterable.
    revoked_reason: Mapped[RevocationReason | None] = mapped_column(
        String(16), nullable=True, default=None
    )

    # Best-effort device label, so a future "your active sessions" screen can show
    # something human. Never trusted for any security decision — the client sends
    # it and the client can send anything.
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    @property
    def is_active(self) -> bool:
        """Usable only if neither revoked nor expired.

        Compared against an aware UTC `now`, which is safe because the column is
        `timestamptz` and asyncpg returns aware datetimes. Comparing an aware and
        a naive datetime raises TypeError in Python, so a mistake here fails
        loudly rather than silently accepting an expired token.
        """
        if self.revoked_at is not None:
            return False
        return self.expires_at > datetime.now(UTC)

    def __repr__(self) -> str:
        return f"<RefreshToken {self.id} user={self.user_id}>"
