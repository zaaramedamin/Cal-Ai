"""Authentication endpoints."""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import CurrentUser
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.db.models.user import RefreshToken, RevocationReason, User
from app.db.session import get_session
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserRead,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# A real argon2 hash of a value nobody knows, verified against when a login names
# an address with no account. Without it, "no such user" returns in ~1ms while a
# wrong password takes ~50ms of deliberate hashing work — and that measurable
# difference lets anyone enumerate which email addresses have accounts. Doing the
# same work in both branches removes the signal.
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))

INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    # Deliberately does not say which half was wrong.
    detail="Incorrect email or password",
    headers={"WWW-Authenticate": "Bearer"},
)

INVALID_REFRESH_TOKEN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired refresh token",
    headers={"WWW-Authenticate": "Bearer"},
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
UserAgentDep = Annotated[str | None, Header(alias="User-Agent")]


async def _issue_token_pair(
    session: AsyncSession, user: User, user_agent: str | None
) -> TokenPair:
    """Mint an access token and a fresh refresh-token session row."""
    settings = get_settings()

    raw_refresh = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
            # Truncated to the column width. An over-long header is a bad reason
            # to fail someone's login.
            user_agent=user_agent[:255] if user_agent else None,
        )
    )

    access_token, expires_at = create_access_token(user.id)
    return TokenPair(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=int((expires_at - datetime.now(UTC)).total_seconds()),
    )


async def _revoke_all_for_user(
    session: AsyncSession, user_id: uuid.UUID, reason: RevocationReason
) -> None:
    """Revoke every active session for a user — the 'sign out everywhere' action."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and sign in",
)
async def register(
    payload: RegisterRequest, session: SessionDep, user_agent: UserAgentDep = None
) -> AuthResponse:
    """Register a new user and return tokens immediately.

    Signing the user straight in avoids making them type the password twice in a
    row for no reason.

    On a duplicate email this returns 409, which does tell an attacker that an
    address is registered. That is a real user-enumeration leak, and it is a
    deliberate trade: the alternative — pretending to succeed and sending a
    disambiguating email — is a genuinely confusing experience, and every
    mainstream app makes the same call. Login, where it matters far more, does
    not leak.
    """
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)

    try:
        # Flush rather than commit: this sends the INSERT so the unique
        # constraint is checked now, while leaving the transaction open so the
        # refresh-token row below commits atomically with it.
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from None

    tokens = await _issue_token_pair(session, user, user_agent)
    await session.commit()
    await session.refresh(user)

    logger.info("Registered user %s", user.id)
    return AuthResponse(**tokens.model_dump(), user=UserRead.model_validate(user))


@router.post("/login", response_model=AuthResponse, summary="Sign in")
async def login(
    payload: LoginRequest, session: SessionDep, user_agent: UserAgentDep = None
) -> AuthResponse:
    """Exchange email and password for a token pair."""
    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None:
        # Burn the same CPU as a real verification before failing. See
        # _DUMMY_PASSWORD_HASH above.
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        raise INVALID_CREDENTIALS

    if not verify_password(payload.password, user.password_hash):
        raise INVALID_CREDENTIALS

    # We have the plaintext here and nowhere else, so this is the only moment we
    # can upgrade a hash created under weaker parameters. Without it, raising the
    # argon2 cost settings would only ever protect accounts created afterwards.
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        logger.info("Upgraded password hash parameters for user %s", user.id)

    tokens = await _issue_token_pair(session, user, user_agent)
    await session.commit()

    return AuthResponse(**tokens.model_dump(), user=UserRead.model_validate(user))


@router.post("/refresh", response_model=TokenPair, summary="Exchange a refresh token")
async def refresh(
    payload: RefreshRequest, session: SessionDep, user_agent: UserAgentDep = None
) -> TokenPair:
    """Rotate a refresh token for a new pair.

    Rotation means the presented token is spent: it is revoked here and a new one
    is issued. That bounds the damage of a stolen token to a single use.

    It also enables theft detection. If a token that was already spent is
    presented again, there are two copies in circulation — the legitimate client
    and a thief — and we cannot tell which is which. The safe response is to
    revoke every session for that user and force a fresh login. Being logged out
    unexpectedly is a far better outcome than an attacker holding a session
    indefinitely.
    """
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()

    if stored is None:
        raise INVALID_REFRESH_TOKEN

    if stored.revoked_at is not None:
        # Only a *spent* token indicates theft. A token revoked by an explicit
        # logout being replayed is almost always a stale client that has not
        # noticed it was signed out — treating that as theft would sign the user
        # out of every other device whenever an old phone retried in the
        # background. See RevocationReason for the full reasoning.
        if stored.revoked_reason == RevocationReason.ROTATED:
            logger.warning(
                "Refresh token reuse detected for user %s — revoking all sessions",
                stored.user_id,
            )
            await _revoke_all_for_user(session, stored.user_id, RevocationReason.REUSE_DETECTED)
            await session.commit()
        raise INVALID_REFRESH_TOKEN

    if stored.expires_at <= datetime.now(UTC):
        raise INVALID_REFRESH_TOKEN

    user = await session.get(User, stored.user_id)
    if user is None:
        raise INVALID_REFRESH_TOKEN

    stored.revoked_at = datetime.now(UTC)
    stored.revoked_reason = RevocationReason.ROTATED
    tokens = await _issue_token_pair(session, user, user_agent)
    await session.commit()

    return tokens


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out this device",
)
async def logout(payload: RefreshRequest, session: SessionDep) -> Response:
    """Revoke one refresh token.

    Returns 204 whether or not the token existed. Logout is not a lookup service:
    reporting "that token was not valid" would let anyone test tokens against
    this endpoint, and there is nothing a caller could usefully do differently.

    Worth being honest about the limit: the *access* token stays valid until it
    expires, because verifying it deliberately involves no database lookup. That
    is the standing trade of stateless access tokens, and it is why theirs is
    measured in minutes.
    """
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(payload.refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
    )
    stored = result.scalar_one_or_none()
    if stored is not None:
        stored.revoked_at = datetime.now(UTC)
        stored.revoked_reason = RevocationReason.LOGOUT
        await session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out every device",
)
async def logout_all(user: CurrentUser, session: SessionDep) -> Response:
    """Revoke every session for the signed-in user.

    Requires a valid access token rather than a refresh token, because this is
    what someone reaches for when they think they have been compromised — and in
    that situation they have the app open, not a refresh token to hand.
    """
    await _revoke_all_for_user(session, user.id, RevocationReason.LOGOUT_ALL)
    await session.commit()
    logger.info("Revoked all sessions for user %s", user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
