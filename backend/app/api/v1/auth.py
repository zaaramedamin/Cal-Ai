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
from app.core.rate_limit import (
    LOGIN_ACCOUNT_MAX_ATTEMPTS,
    LOGIN_ACCOUNT_WINDOW_SECONDS,
    clear_failures,
    is_blocked,
    login_rate_limit,
    password_reset_confirm_rate_limit,
    password_reset_request_rate_limit,
    record_failure,
    refresh_rate_limit,
    register_rate_limit,
)
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.db.models.user import PasswordResetToken, RefreshToken, RevocationReason, User
from app.db.session import get_session
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetRequested,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserRead,
)
from app.services.email import send_password_reset

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

def _too_many_attempts(retry_after_seconds: float) -> HTTPException:
    """A 429 that tells the caller how long to wait.

    RFC 6585 requires Retry-After on a 429, and the mobile app shows the wait
    rather than letting the user hammer a button that cannot work. Easy to omit
    on a hand-built exception — the per-IP limiter sets it, so an account-level
    429 without it would be silently inconsistent.
    """
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many sign-in attempts for this account. Please wait and try again.",
        headers={"Retry-After": str(max(1, int(retry_after_seconds) + 1))},
    )


async def _record_login_failure(email: str) -> None:
    await record_failure(
        "login-account",
        email,
        times=LOGIN_ACCOUNT_MAX_ATTEMPTS,
        seconds=LOGIN_ACCOUNT_WINDOW_SECONDS,
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
    dependencies=[Depends(register_rate_limit)],
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


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Sign in",
    dependencies=[Depends(login_rate_limit)],
)
async def login(
    payload: LoginRequest, session: SessionDep, user_agent: UserAgentDep = None
) -> AuthResponse:
    """Exchange email and password for a token pair.

    Limited twice over: by IP through the dependency above, and per-account
    below. The per-account limit is the one that matters against a botnet, where
    every request comes from a different address and no per-IP budget is ever
    reached.
    """
    account_key = payload.email.strip()

    blocked_for = await is_blocked(
        "login-account",
        account_key,
        times=LOGIN_ACCOUNT_MAX_ATTEMPTS,
        seconds=LOGIN_ACCOUNT_WINDOW_SECONDS,
    )
    if blocked_for is not None:
        raise _too_many_attempts(blocked_for)

    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None:
        # Burn the same CPU as a real verification before failing. See
        # _DUMMY_PASSWORD_HASH above.
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        await _record_login_failure(account_key)
        raise INVALID_CREDENTIALS

    if not verify_password(payload.password, user.password_hash):
        await _record_login_failure(account_key)
        raise INVALID_CREDENTIALS

    # Successful login wipes the account's failure count. Otherwise someone who
    # mistypes four times then succeeds still carries four strikes, and a later
    # genuine slip locks them out. Limits should punish failure, not use.
    await clear_failures("login-account", account_key)

    # We have the plaintext here and nowhere else, so this is the only moment we
    # can upgrade a hash created under weaker parameters. Without it, raising the
    # argon2 cost settings would only ever protect accounts created afterwards.
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        logger.info("Upgraded password hash parameters for user %s", user.id)

    tokens = await _issue_token_pair(session, user, user_agent)
    await session.commit()

    return AuthResponse(**tokens.model_dump(), user=UserRead.model_validate(user))


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Exchange a refresh token",
    dependencies=[Depends(refresh_rate_limit)],
)
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
    "/password-reset/request",
    response_model=PasswordResetRequested,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset link",
    dependencies=[Depends(password_reset_request_rate_limit)],
)
async def request_password_reset(
    payload: PasswordResetRequest, session: SessionDep
) -> PasswordResetRequested:
    """Send a reset link, if the account exists.

    Always 202 with the same message. Answering differently for an unknown
    address would make this a free tool for discovering who has an account, and
    unlike registration there is no usability cost to staying quiet — the message
    reads naturally whether or not the address is registered.

    202 Accepted rather than 200 OK is the honest status: we have accepted the
    request, and delivery happens outside this response.
    """
    result = await session.execute(select(User).where(User.email == payload.email.strip()))
    user = result.scalar_one_or_none()

    if user is None:
        # Deliberately silent. Same shape, same timing budget, no hint.
        logger.info("Password reset requested for unknown address")
        return PasswordResetRequested()

    # Invalidate any outstanding links first, so requesting a second one makes
    # the first dead. Otherwise every request a user makes leaves another live
    # key to their account sitting in their inbox.
    await session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=datetime.now(UTC))
    )

    raw_token = generate_refresh_token()
    settings = get_settings()
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(UTC)
            + timedelta(minutes=settings.password_reset_expire_minutes),
        )
    )
    await session.commit()

    send_password_reset(user.email, raw_token)
    logger.info("Password reset issued for user %s", user.id)

    return PasswordResetRequested(
        debug_reset_token=raw_token if settings.is_development else None
    )


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set a new password using a reset token",
    dependencies=[Depends(password_reset_confirm_rate_limit)],
)
async def confirm_password_reset(payload: PasswordResetConfirm, session: SessionDep) -> Response:
    """Consume a reset token and set the new password.

    Revoking every refresh token afterwards is the part that makes this a real
    recovery mechanism rather than a convenience. Someone resetting their
    password has usually either forgotten it or believes they were compromised —
    and in the second case, leaving the attacker's existing sessions alive would
    make the reset almost pointless. The attacker holds a refresh token, not the
    password, so changing the password alone does not touch them.
    """
    result = await session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_refresh_token(payload.token)
        )
    )
    reset = result.scalar_one_or_none()

    # One error for every failure mode — unknown, spent, expired. Distinguishing
    # them would let someone probe which tokens ever existed.
    if reset is None or not reset.is_usable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired. Request a new one.",
        )

    user = await session.get(User, reset.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired. Request a new one.",
        )

    user.password_hash = hash_password(payload.new_password)
    reset.used_at = datetime.now(UTC)
    await _revoke_all_for_user(session, user.id, RevocationReason.PASSWORD_RESET)

    # The account was locked out of logging in; a successful reset should clear
    # that, or the user fixes their password and still cannot get in.
    await clear_failures("login-account", user.email)

    await session.commit()
    logger.info("Password reset completed for user %s; all sessions revoked", user.id)

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
