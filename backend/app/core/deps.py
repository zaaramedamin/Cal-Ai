"""Shared FastAPI dependencies.

`get_current_user` is the "protected route middleware" of the brief. It is a
dependency rather than middleware on purpose: middleware runs on every request
and would need a list of which paths to skip, which drifts out of date the moment
someone adds a route. A dependency is opted into per endpoint, so a protected
route is protected because its signature says so — visible in the code, and
impossible to forget by editing a config file somewhere else.

**Two token formats are accepted while auth moves to Supabase.** A Supabase
ES256 token is tried first; anything it rejects falls through to the hand-built
HS256 one. That is what lets the mobile app keep working screen by screen instead
of everything breaking on the day the backend switches — and the fallback is
deleted, not left lying around, once the app no longer issues legacy tokens.

The order matters and is not arbitrary: the legacy path trusts `SECRET_KEY`,
which we hold, so trying it first would mean a forged-but-well-formed legacy
token got a signature check before a genuine Supabase one. Supabase first keeps
the stronger scheme authoritative.
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.core.supabase_auth import (
    InvalidSupabaseToken,
    email_from,
    user_id_from,
    verify_token,
)
from app.db.models.user import User
from app.db.session import get_session

logger = logging.getLogger(__name__)

# auto_error=False so a missing header reaches our code and produces the same
# 401 as a bad one. With the default, FastAPI raises a 403 for "no header" and
# our 401 for "bad header" — two different statuses for one situation, which the
# mobile client would then have to special-case.
_bearer = HTTPBearer(auto_error=False, description="Supabase access token")

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    # Required by the HTTP spec for 401, and it is the signal the mobile client
    # keys on to decide "try refreshing the token" rather than "show an error".
    headers={"WWW-Authenticate": "Bearer"},
)


async def _provision(session: AsyncSession, user_id: UUID, email: str) -> User:
    """Find or create the local row for a Supabase-authenticated account.

    Supabase owns the credential; this table owns everything about the person
    that the app cares about — their profile, timezone, and the foreign keys
    from their diary. The row has to exist before any of that can be written, and
    the first authenticated request is the earliest moment we know the account is
    real, so it is created here rather than by a signup endpoint we no longer own.

    `ON CONFLICT DO NOTHING` rather than select-then-insert: a phone that fires
    several requests the instant it signs in would otherwise have two of them
    find nothing and both insert, turning a race into a 500 on the user's very
    first screen.

    Deliberately *unqualified* — no `index_elements`. Naming the id constraint
    covers the ordinary repeat visit and leaves the interesting case unhandled:
    a Supabase account whose email already belongs to a different local account.
    That raises a unique violation on `email` instead, and unqualified DO NOTHING
    turns it into "no row inserted", which the lookup below reads as a refusal.
    """
    statement = (
        pg_insert(User)
        .values(id=user_id, email=email, password_hash=None)
        .on_conflict_do_nothing()
    )
    await session.execute(statement)
    await session.commit()

    user = await session.get(User, user_id)
    if user is None:
        # Only reachable if the insert conflicted on `email` rather than `id` —
        # the same address already held by a different account. Refusing beats
        # silently attaching this login to somebody else's diary.
        logger.warning("Could not provision Supabase user %s (%s)", user_id, email)
        raise CREDENTIALS_EXCEPTION

    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Resolve the caller's access token to a User, or reject with 401.

    Every failure returns the same opaque 401. Distinguishing "malformed token"
    from "expired" from "user no longer exists" would help a legitimate user
    debug approximately never, and helps an attacker probe constantly.
    """
    if credentials is None:
        raise CREDENTIALS_EXCEPTION

    token = credentials.credentials

    if get_settings().supabase_auth_enabled:
        try:
            claims = await verify_token(token)
        except InvalidSupabaseToken:
            pass  # Not a Supabase token; the legacy path below may still accept it.
        else:
            email = email_from(claims)
            if email is None:
                # Every Supabase account in this app signs in with email, and the
                # local row requires one. A token without it is not something to
                # guess a value for.
                raise CREDENTIALS_EXCEPTION
            return await _provision(session, UUID(user_id_from(claims)), email)

    # --- legacy, hand-built auth. Deleted once the app stops issuing these. ---
    user_id = decode_access_token(token)
    if user_id is None:
        raise CREDENTIALS_EXCEPTION

    # The token is validly signed, but the user may have been deleted since it
    # was issued. A JWT proves what was true when it was minted, not what is true
    # now, so the row still has to be looked up.
    user = await session.get(User, user_id)
    if user is None:
        raise CREDENTIALS_EXCEPTION

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
"""Alias so endpoints read `user: CurrentUser` instead of repeating the Depends."""
