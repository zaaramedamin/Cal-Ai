"""Verifying access tokens issued by Supabase Auth.

Supabase signs with **ES256** and publishes the matching public keys at a JWKS
endpoint. That shape is what makes this simple and safe:

* The server holds no secret. Verification needs only a public key, so there is
  nothing here worth stealing — unlike the hand-built auth, where `SECRET_KEY`
  can mint a token for any account.
* Keys can rotate without a deploy. A token signed by a key we have not seen
  makes us refetch once; if it is genuinely new, it verifies and life continues.

**What is checked, and why each one matters.** A JWT library will happily decode
a token without validating anything, and every omission below is a real bypass:

* **signature** — obviously. Also `algorithms=["ES256"]` explicitly, because
  accepting `alg` from the token is the classic JWT forgery: a token claiming
  `alg: none`, or `HS256` signed with the *public* key as the HMAC secret.
* **`exp`** — otherwise a token stolen once works forever.
* **`aud` = "authenticated"** — Supabase issues other audiences; an anon token
  must not read a user's diary.
* **`iss`** — pins tokens to *this* project. Without it, anyone's Supabase
  project could mint tokens our API accepts, and creating one is free.
"""

import logging
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWK

from app.core.config import get_settings
from app.core.tls import use_system_trust_store

logger = logging.getLogger(__name__)

#: Supabase's audience for a signed-in user.
AUDIENCE = "authenticated"

#: Only ES256. See the module docstring — a list that accepts more is a bypass.
ALGORITHMS = ["ES256"]

#: How long a fetched key set is trusted before being refetched.
#:
#: Ten minutes is a compromise: long enough that verification is a local
#: operation rather than an HTTP call, short enough that a revoked key stops
#: working promptly. An unknown `kid` also forces an immediate refetch, so
#: ordinary rotation is handled without waiting for this to expire.
CACHE_SECONDS = 600


class InvalidSupabaseToken(Exception):
    """The token is missing, malformed, expired, or not ours.

    One exception for every failure on purpose. Distinguishing "expired" from
    "bad signature" in the response tells an attacker which half of a forgery
    attempt worked; the client's correct action is identical either way.
    """


class _KeyCache:
    """The project's public keys, refetched on expiry or on an unknown `kid`."""

    def __init__(self) -> None:
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at: float = 0.0

    def _stale(self) -> bool:
        return time.monotonic() - self._fetched_at > CACHE_SECONDS

    async def _fetch(self) -> None:
        settings = get_settings()
        use_system_trust_store()

        async with httpx.AsyncClient(timeout=10) as http:
            response = await http.get(settings.supabase_jwks_url)
        response.raise_for_status()

        keys: dict[str, PyJWK] = {}
        for raw in response.json().get("keys", []):
            kid = raw.get("kid")
            if kid:
                keys[kid] = PyJWK.from_dict(raw)

        if not keys:
            raise InvalidSupabaseToken("Supabase published no signing keys.")

        self._keys = keys
        self._fetched_at = time.monotonic()
        logger.info("Fetched %d Supabase signing key(s)", len(keys))

    async def get(self, kid: str) -> PyJWK:
        if self._stale() or not self._keys:
            await self._fetch()

        if kid not in self._keys:
            # Rotation: Supabase started signing with a key minted after our last
            # fetch. Refetch once. Doing this unconditionally would let anyone
            # force an outbound request per bogus token, so it happens only after
            # the cache has already been consulted.
            logger.info("Unknown signing key %s, refetching", kid[:8])
            await self._fetch()

        if kid not in self._keys:
            raise InvalidSupabaseToken("Token signed by an unknown key.")

        return self._keys[kid]

    def clear(self) -> None:
        """Drop the cache. For tests, and for a manual refresh."""
        self._keys = {}
        self._fetched_at = 0.0


_cache = _KeyCache()


def reset_key_cache() -> None:
    _cache.clear()


async def verify_token(token: str) -> dict[str, Any]:
    """Verify a Supabase access token and return its claims.

    Raises `InvalidSupabaseToken` for anything that is not a currently-valid
    token from this project.
    """
    settings = get_settings()
    if not settings.supabase_auth_enabled:
        raise InvalidSupabaseToken("Supabase Auth is not configured.")

    try:
        # Read the header *without* verifying, purely to learn which key to ask
        # for. Nothing from here is trusted — `jwt.decode` below re-reads the
        # header and enforces the algorithm itself.
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError as exc:
        raise InvalidSupabaseToken("Malformed token.") from exc

    if not kid:
        raise InvalidSupabaseToken("Token has no key id.")

    key = await _cache.get(kid)

    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=ALGORITHMS,
            audience=AUDIENCE,
            issuer=settings.supabase_issuer,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        # Logged at debug, not warning: a expired token is a normal event that
        # happens to every user every hour, and logging it as a problem trains
        # people to ignore the log.
        logger.debug("Rejected Supabase token: %s", exc)
        raise InvalidSupabaseToken("Token is not valid.") from exc

    return claims


def user_id_from(claims: dict[str, Any]) -> str:
    """The Supabase user id — the `sub` claim, and our `users.id`.

    Supabase issues UUIDs, which is what lets the existing primary key and every
    foreign key referencing it stay exactly as they are.
    """
    return str(claims["sub"])


def email_from(claims: dict[str, Any]) -> str | None:
    """The verified email, when the token carries one."""
    email = claims.get("email")
    return str(email) if email else None
