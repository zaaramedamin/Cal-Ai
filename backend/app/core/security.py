"""Password hashing and token handling.

Two different secrets live here and they are protected in deliberately different
ways. Understanding why is the important part:

**Passwords** are low-entropy — people pick `hunter2`, and they reuse it on other
sites. So they get hashed with argon2id, which is *deliberately slow and memory
hungry*. If our database leaks, an attacker with a GPU farm should still be
unable to work backwards to the plaintext.

**Refresh tokens** are 256 bits of cryptographic randomness that we generated.
Nobody guesses one, so a slow hash buys nothing and would cost real latency on
every refresh. They get a plain SHA-256, which is fast and entirely sufficient.

Using argon2 for both would be cargo-culting; using SHA-256 for both would be a
serious vulnerability. The choice follows from the entropy of the input.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

ALGORITHM = "HS256"

TokenType = Literal["access"]

# Defaults follow the argon2-cffi maintainers' current recommendation, which
# tracks the OWASP Password Storage Cheat Sheet. argon2id is the hybrid variant:
# resistant to both GPU cracking and side-channel attacks, and it is the variant
# RFC 9106 tells you to pick when you have no reason to choose otherwise.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage.

    The returned string embeds the algorithm, parameters and a per-password
    random salt, so no separate salt column is needed and the cost parameters can
    be raised later without invalidating existing hashes.
    """
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against a stored hash.

    Returns False rather than raising on a mismatch, because at the call site a
    wrong password is an expected outcome, not an exceptional one. A malformed
    hash is treated the same way: it means that row is unusable, which is a
    failed login, not a 500.
    """
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def password_needs_rehash(password_hash: str) -> bool:
    """True when a stored hash used weaker parameters than we now require.

    Lets us transparently upgrade a user's hash on their next successful login,
    so raising the cost parameters actually protects existing accounts instead of
    only new ones.
    """
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(user_id: uuid.UUID) -> tuple[str, datetime]:
    """Issue a signed access token. Returns the token and its expiry.

    The token carries the user id and nothing else that matters. It is signed,
    not encrypted — anyone holding it can read the payload, so it must never
    contain anything private. Its value is that it cannot be *modified* without
    the secret.
    """
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=get_settings().access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        # Distinguishes token kinds. Without it, a token minted for one purpose
        # could be replayed against an endpoint expecting another — a classic
        # JWT confusion bug.
        "type": "access",
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITHM), expires_at


def decode_access_token(token: str) -> uuid.UUID | None:
    """Verify an access token and return its subject, or None if unusable.

    `algorithms=[ALGORITHM]` is not optional. Left open, a caller could hand us a
    token whose header says `alg: none` and PyJWT would happily "verify" it —
    the single most famous JWT vulnerability. Pinning the algorithm closes it.
    """
    try:
        payload = jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.PyJWTError:
        # Covers expiry, bad signature, malformed structure and missing claims.
        # The caller only needs to know it is not a valid token.
        return None

    if payload.get("type") != "access":
        return None

    try:
        return uuid.UUID(payload["sub"])
    except (ValueError, TypeError, KeyError):
        return None


def generate_refresh_token() -> str:
    """Create an opaque refresh token.

    Deliberately *not* a JWT. A JWT is self-validating, which is exactly wrong
    here: we need every refresh to consult the database so a revoked token stops
    working immediately. An opaque random string forces that lookup, which makes
    logout and theft detection actually possible.

    32 bytes is 256 bits of entropy — unguessable by any practical means.
    """
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage.

    We store this, never the token itself. A refresh token in the database is a
    live credential: anyone reading the table could impersonate any user
    indefinitely. Storing only the hash means a database leak is bad but not
    instantly game over — the same reasoning as passwords, just with a cheaper
    hash because the input is already random.
    """
    return hashlib.sha256(token.encode()).hexdigest()
