"""Rate limiting for authentication endpoints.

Without this, nothing stops an attacker sending thousands of password guesses a
minute. argon2 makes each guess expensive for *us* as well as them — roughly
50ms of CPU and 64MB of memory per attempt — so an unlimited login endpoint is
simultaneously a credential-stuffing surface and a denial-of-service one.

**Implementation: an in-process sliding-window log.**

The honest limitation, stated up front: this counter lives in the memory of one
Python process. Run two uvicorn workers and each keeps its own tally, so the
effective limit doubles; restart the process and it resets. That is acceptable
for a single-process deployment and is a real weakness at scale.

The fix is to move the counter to Redis, where every worker shares one view.
That is a Phase 7 concern — it needs infrastructure we do not have yet, and the
interface here is deliberately shaped so the swap touches only this file.

A sliding-window *log* (keeping timestamps) rather than a fixed window (counting
per calendar minute), because a fixed window allows a burst of 2x the limit
across a boundary: ten attempts at 10:00:59 and ten more at 10:01:00.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


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


class SlidingWindowCounter:
    """Timestamps of recent hits, per key."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
        """Record an attempt. Returns seconds to wait if over the limit, else None.

        `time.monotonic` rather than wall-clock time: it cannot jump backwards
        when the system clock is adjusted or a leap second lands, which would
        otherwise let an attacker's window silently reset.
        """
        now = time.monotonic()
        cutoff = now - window_seconds
        hits = self._hits[key]

        # Drop anything that has aged out of the window.
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= limit:
            return max(0.0, hits[0] + window_seconds - now)

        hits.append(now)
        return None

    def peek(self, key: str, limit: int, window_seconds: float) -> float | None:
        """Seconds to wait if `key` is over its limit, without recording a hit.

        Separate from `hit` because checking must not itself consume budget —
        otherwise merely asking "is this account locked?" would lock it.
        """
        hits = self._hits.get(key)
        if not hits:
            return None

        now = time.monotonic()
        cutoff = now - window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= limit:
            return max(0.0, hits[0] + window_seconds - now)
        return None

    def reset(self, key: str) -> None:
        """Forget a key — called after a *successful* login.

        Without this, someone who mistypes their password four times and then
        gets it right still carries those four strikes, and a later genuine
        mistake locks them out. Limits should punish failure, not use.
        """
        self._hits.pop(key, None)

    def clear(self) -> None:
        self._hits.clear()


_counter = SlidingWindowCounter()


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
        retry_after = _counter.hit(key, self.times, self.seconds)
        if retry_after is None:
            return

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait and try again.",
            # Required by RFC 6585 for 429, and the mobile client shows the wait
            # rather than letting the user hammer a dead button.
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )


def record_failure(scope: str, identifier: str, *, times: int, seconds: int) -> None:
    """Count a failure against a non-IP key, such as an email address.

    IP-based limits alone are weak against a distributed attack: a botnet gives
    an attacker thousands of addresses, each staying under the per-IP budget
    while collectively hammering one account. Counting per-account as well means
    a single victim cannot be brute-forced no matter how many sources are used.
    """
    if get_settings().rate_limit_enabled:
        _counter.hit(f"{scope}:{identifier.lower()}", times, seconds)


def is_blocked(scope: str, identifier: str, *, times: int, seconds: int) -> float | None:
    """Check a non-IP key without recording a hit."""
    if not get_settings().rate_limit_enabled:
        return None
    return _counter.peek(f"{scope}:{identifier.lower()}", times, seconds)


def clear_failures(scope: str, identifier: str) -> None:
    _counter.reset(f"{scope}:{identifier.lower()}")


def reset_all() -> None:
    """Wipe every counter. Test-only — limits would otherwise leak across tests."""
    _counter.clear()


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
