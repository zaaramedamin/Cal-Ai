"""Where rate-limit counters actually live.

Two implementations of one interface. The policy — which endpoint gets which
budget — is in `rate_limit.py`; this file is only the counting.

**In memory.** A sliding-window log per key, in the memory of one Python
process. Correct and fast, with one honest limitation: run two uvicorn workers
and each keeps its own tally, so the effective limit doubles. Restart the
process and every counter resets. Fine for one process on a laptop.

**In Redis.** The same sliding window, in a sorted set every worker shares. This
is what makes the limit mean what it says once more than one process serves
traffic, which is the normal shape of any real deployment.

Both are a sliding-window *log* — timestamps kept, not a count per calendar
minute. A fixed window lets an attacker send the full budget just before the
boundary and again just after, at twice the intended rate: ten attempts at
10:00:59 and ten more at 10:01:00.

**When Redis is unreachable, the Redis store falls back to the in-memory one**
rather than failing the request. The alternative readings of a Redis outage are
both worse. Fail closed and a dead cache locks every user out of their own
account; fail open and an outage becomes the window an attacker was waiting
for. Degrading to per-process limiting keeps the door shut, just less tightly,
and says so in the log.
"""

import logging
import secrets
import time
from collections import defaultdict, deque
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: Prefix on every Redis key. Redis has no schemas, so a shared instance — the
#: normal case on a hosted free tier — is one flat namespace. This is what stops
#: a rate-limit key colliding with something else that happens to live there.
KEY_PREFIX = "calai:rl:"


class Store(Protocol):
    """The counting interface. Async because one implementation talks to Redis."""

    async def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
        """Record an attempt. Returns seconds to wait if over the limit, else None."""
        ...

    async def peek(self, key: str, limit: int, window_seconds: float) -> float | None:
        """Seconds to wait if `key` is over its limit, without recording a hit."""
        ...

    async def reset(self, key: str) -> None:
        """Forget a key."""
        ...


# --------------------------------------------------------------------------- #
# In-process
# --------------------------------------------------------------------------- #


class MemoryStore:
    """Timestamps of recent hits, per key, in this process only."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
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

    async def peek(self, key: str, limit: int, window_seconds: float) -> float | None:
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

    async def reset(self, key: str) -> None:
        """Forget a key — called after a *successful* login.

        Without this, someone who mistypes their password four times and then
        gets it right still carries those four strikes, and a later genuine
        mistake locks them out. Limits should punish failure, not use.
        """
        self._hits.pop(key, None)

    def clear(self) -> None:
        self._hits.clear()


# --------------------------------------------------------------------------- #
# Redis
# --------------------------------------------------------------------------- #

#: Record a hit and report whether it was over the limit — atomically.
#:
#: Lua rather than a pipeline because the read and the write have to be one
#: step. Between `ZCARD` and `ZADD` from Python, another worker can add its own
#: entry; both see room and both write, and the limit is quietly exceeded. That
#: race is the entire reason a shared counter is harder than a local one, and a
#: script is how Redis lets you not have it.
#:
#: `TIME` is read inside the script so every worker scores against the Redis
#: server's clock. This is not a nicety: `time.monotonic()` has a per-process
#: epoch, so timestamps from two workers are not comparable at all, and even
#: wall-clock times drift between hosts.
_HIT = """
local now = redis.call('TIME')
local now_ms = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
local window_ms = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])

redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now_ms - window_ms)

if redis.call('ZCARD', KEYS[1]) >= limit then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  return math.ceil(tonumber(oldest[2]) + window_ms - now_ms)
end

-- ARGV[3] is a random member, not the timestamp. A sorted set holds each member
-- once, so two hits landing in the same millisecond with the timestamp as their
-- member would collapse into a single entry and one of them would not be
-- counted. Under exactly the concurrency this store exists to handle.
redis.call('ZADD', KEYS[1], now_ms, ARGV[3])

-- Without this every address that ever touched /login stays in Redis forever.
-- The window is the natural lifetime: once the newest entry ages out there is
-- nothing left worth keeping.
redis.call('PEXPIRE', KEYS[1], window_ms)
return -1
"""

#: Read-only twin of `_HIT`. It counts within the window instead of trimming to
#: it, so asking whether a key is blocked writes nothing at all.
_PEEK = """
local now = redis.call('TIME')
local now_ms = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
local window_ms = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local cutoff = now_ms - window_ms

if redis.call('ZCOUNT', KEYS[1], cutoff, '+inf') < limit then
  return -1
end

local oldest = redis.call('ZRANGEBYSCORE', KEYS[1], cutoff, '+inf', 'WITHSCORES', 'LIMIT', 0, 1)
return math.ceil(tonumber(oldest[2]) + window_ms - now_ms)
"""


class RedisStore:
    """A sliding-window log in a Redis sorted set, shared by every worker.

    Falls back to `fallback` on any Redis failure. See the module docstring for
    why that is the least-bad of the three options.
    """

    def __init__(self, url: str, fallback: MemoryStore) -> None:
        self.url = url
        self._fallback = fallback
        self._client = None
        self._hit_script = None
        self._peek_script = None
        self._warned = False

    def _connect(self):
        """Build the client on first use.

        Lazily, because constructing it at import time would make the module
        unimportable without the dependency installed, and because a URL that
        points nowhere should fail on a request we can log rather than at boot.
        """
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(self.url, decode_responses=True)
            self._hit_script = self._client.register_script(_HIT)
            self._peek_script = self._client.register_script(_PEEK)
        return self._client

    def _degrade(self, exc: Exception) -> None:
        """Log the first failure of an outage loudly, then stay quiet.

        An outage under load would otherwise write one line per request and bury
        everything else in the log. The first line is the one that matters.
        """
        if not self._warned:
            self._warned = True
            logger.error(
                "Redis unreachable (%s) — rate limiting has fallen back to per-process "
                "counters. Limits are now enforced per worker, not across the fleet.",
                exc,
            )

    def _recovered(self) -> None:
        """Re-arm the warning after a call succeeds.

        Every call still tries Redis, so coming back is automatic — but without
        this the flag latches on the first failure ever seen, and the *second*
        outage a process lives through passes in silence. One line per outage,
        not one line per process lifetime.
        """
        if self._warned:
            self._warned = False
            logger.info("Redis is answering again — rate limit counters are shared once more.")

    async def _eval(self, script, key: str, limit: int, window_seconds: float, *extra):
        result = await script(
            keys=[KEY_PREFIX + key],
            args=[int(window_seconds * 1000), limit, *extra],
        )
        self._recovered()
        # -1 is "under the limit". Lua cannot return nil distinguishably — it
        # converts to false, and then to None, which is also a valid answer here.
        return None if int(result) < 0 else int(result) / 1000

    async def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
        try:
            self._connect()
            return await self._eval(
                self._hit_script, key, limit, window_seconds, secrets.token_hex(8)
            )
        except Exception as exc:  # noqa: BLE001 - degrade, never fail the request
            self._degrade(exc)
            return await self._fallback.hit(key, limit, window_seconds)

    async def peek(self, key: str, limit: int, window_seconds: float) -> float | None:
        try:
            self._connect()
            return await self._eval(self._peek_script, key, limit, window_seconds)
        except Exception as exc:  # noqa: BLE001
            self._degrade(exc)
            return await self._fallback.peek(key, limit, window_seconds)

    async def reset(self, key: str) -> None:
        try:
            await self._connect().delete(KEY_PREFIX + key)
        except Exception as exc:  # noqa: BLE001
            self._degrade(exc)
        # Always clear the local copy too: a fallback during the outage may have
        # recorded failures here, and a successful login must forgive both.
        await self._fallback.reset(key)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._hit_script = None
            self._peek_script = None


# --------------------------------------------------------------------------- #
# Choosing one
# --------------------------------------------------------------------------- #

_memory = MemoryStore()
_redis: RedisStore | None = None


def get_store() -> Store:
    """The store this process should count in.

    Redis when `REDIS_URL` is set, memory otherwise. Deciding per call rather
    than once at import keeps the test suite able to change the setting, and
    costs one attribute lookup.
    """
    global _redis

    url = get_settings().redis_url
    if not url:
        return _memory

    if _redis is None or _redis.url != url:
        _redis = RedisStore(url, fallback=_memory)
    return _redis


async def close_store() -> None:
    """Release the Redis connection on shutdown."""
    if _redis is not None:
        await _redis.close()


def clear_memory() -> None:
    """Wipe the in-process counters. Test-only.

    Redis-backed tests clean up their own keys; there is no FLUSHDB here because
    the configured Redis may not be exclusively ours.
    """
    _memory.clear()
