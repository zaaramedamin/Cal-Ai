"""Shared FastAPI dependencies.

`get_current_user` is the "protected route middleware" of the brief. It is a
dependency rather than middleware on purpose: middleware runs on every request
and would need a list of which paths to skip, which drifts out of date the moment
someone adds a route. A dependency is opted into per endpoint, so a protected
route is protected because its signature says so — visible in the code, and
impossible to forget by editing a config file somewhere else.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.models.user import User
from app.db.session import get_session

# auto_error=False so a missing header reaches our code and produces the same
# 401 as a bad one. With the default, FastAPI raises a 403 for "no header" and
# our 401 for "bad header" — two different statuses for one situation, which the
# mobile client would then have to special-case.
_bearer = HTTPBearer(auto_error=False, description="Access token from /auth/login")

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    # Required by the HTTP spec for 401, and it is the signal the mobile client
    # keys on to decide "try refreshing the token" rather than "show an error".
    headers={"WWW-Authenticate": "Bearer"},
)


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

    user_id = decode_access_token(credentials.credentials)
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
