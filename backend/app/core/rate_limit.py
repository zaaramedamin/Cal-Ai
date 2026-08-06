"""Rate limiting for authentication endpoints.

Without this, nothing stops an attacker sending thousands of password guesses a
minute. argon2 makes each guess expensive for *us* as well as them — roughly
50ms of CPU and 64MB of memory per attempt — so an unlimited login endpoint is
simultaneously a credential-stuffing surface and a denial-of-service one.

This file is the *policy*: which endpoint gets which budget, and what a client
is identified by. The counting itself lives in `rate_limit_store.py`, which
keeps the tally in Redis when `REDIS_URL` is set and in this process's memory
when it is not. Nothing here needs to know which.

Two kinds of key, and the second is the one that matters:

* **Per IP**, via the `RateLimit` dependency. Stops one machine hammering an
  endpoint.
* **Per account**, via `record_failure`. A botnet gives an attacker thousands
  of addresses, each staying comfortably under a per-IP budget while
  collectively brute-forcing one victim. Counting per account means the victim
  is safe no matter how many sources are used.
"""

from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.core.rate_limit_store import clear_memory, get_store


def client_ip(request: Request) -> str:
    """Best-effort client address.

    `X-Forwarded-For` is only consulted when we are explicitly configured to sit
    behind a proxy. Trusting it unconditionally would make rate limiting useless:
    a client can send any value it likes, so every request could claim a fresh
    address and never hit a limit.
    """
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Left-most entry is the original client; the rest are proxy hops.
            return forwarded.split(",")[0].strip()

    return request.client.host if request.client else "unknown"


class RateLimit:
    """A FastAPI dependency enforcing one limit.

    Used as `Depends(...)` rather than middleware so each endpoint declares its
    own budget. Login and password-reset deserve far tighter limits than reading
    a diary entry, and a single global middleware cannot express that without a
    path-matching table that drifts out of date.
    """

    def __init__(self, *, times: int, seconds: int, scope: str) -> None:
        self.times = times
        self.seconds = seconds
        self.scope = scope

    async def __call__(self, request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return

        key = f"{self.scope}:{client_ip(request)}"
        retry_after = await get_store().hit(key, self.times, self.seconds)
        if retry_after is None:
            return

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait and try again.",
            # Required by RFC 6585 for 429, and the mobile client shows the wait
            # rather than letting the user hammer a dead button.
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )


async def record_failure(scope: str, identifier: str, *, times: int, seconds: int) -> None:
    """Count a failure against a non-IP key, such as an email address."""
    if get_settings().rate_limit_enabled:
        await get_store().hit(f"{scope}:{identifier.lower()}", times, seconds)


async def is_blocked(scope: str, identifier: str, *, times: int, seconds: int) -> float | None:
    """Check a non-IP key without recording a hit."""
    if not get_settings().rate_limit_enabled:
        return None
    return await get_store().peek(f"{scope}:{identifier.lower()}", times, seconds)


async def clear_failures(scope: str, identifier: str) -> None:
    """Forget a key — called after a *successful* login.

    Without this, someone who mistypes their password four times and then gets
    it right still carries those four strikes, and a later genuine mistake locks
    them out. Limits should punish failure, not use.
    """
    await get_store().reset(f"{scope}:{identifier.lower()}")


def reset_all() -> None:
    """Wipe every in-process counter. Test-only — limits would otherwise leak
    across tests."""
    clear_memory()


# --------------------------------------------------------------------------- #
# The limits themselves.
#
# Numbers chosen to be invisible to a real person and painful to a script. A
# human mistypes a password two or three times, not ten; nobody registers five
# accounts an hour from one address by accident.
# --------------------------------------------------------------------------- #

LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 300

#: Per-account, so a distributed attack on one victim still hits a wall.
LOGIN_ACCOUNT_MAX_ATTEMPTS = 8
LOGIN_ACCOUNT_WINDOW_SECONDS = 900

login_rate_limit = RateLimit(times=LOGIN_MAX_ATTEMPTS, seconds=LOGIN_WINDOW_SECONDS, scope="login")
register_rate_limit = RateLimit(times=5, seconds=3600, scope="register")
refresh_rate_limit = RateLimit(times=60, seconds=3600, scope="refresh")

#: Deliberately strict. Each request sends an email, so an unlimited endpoint is
#: a way to use our server to spam somebody else's inbox.
password_reset_request_rate_limit = RateLimit(times=5, seconds=3600, scope="password-reset-request")

#: Separate scope from the request limit, and more generous.
#:
#: Sharing one budget was a real bug: a user requests a link (1 hit), then
#: mistypes their new password a few times, and each rejected submission burns
#: the same budget — locking them out of completing their own reset. The two
#: endpoints have different risks and deserve different budgets.
#:
#: This one only needs to stop token brute-forcing, and the token is 256 bits, so
#: guessing is hopeless regardless. The limit is here to cap abuse, not to be the
#: primary defence.
password_reset_confirm_rate_limit = RateLimit(
    times=20, seconds=3600, scope="password-reset-confirm"
)
