"""The shared rate-limit counter.

Two halves, and they need different things.

The **fallback** tests need no server at all — they prove that a broken Redis
degrades to per-process counting instead of failing the request, which is the
behaviour nobody would notice was missing until an outage.

The **store** tests need a real Redis, because the interesting part is a Lua
script and there is no honest way to test Lua without Redis running it. A fake
would only prove the fake works. They are skipped, loudly, when nothing answers
on `REDIS_TEST_URL` (default: the local compose container), so the suite still
passes for someone who has not started it.

    docker compose up -d redis
"""

import asyncio
import os
import uuid

import pytest

from app.core.rate_limit_store import KEY_PREFIX, MemoryStore, RedisStore, get_store

REDIS_URL = os.environ.get("REDIS_TEST_URL", "redis://127.0.0.1:6379/15")


async def _redis_available() -> bool:
    try:
        from redis.asyncio import Redis
    except ImportError:  # pragma: no cover - redis is a declared dependency
        return False

    client = Redis.from_url(REDIS_URL)
    try:
        await client.ping()
        return True
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return False
    finally:
        await client.aclose()


requires_redis = pytest.mark.skipif(
    not asyncio.run(_redis_available()),
    reason=f"no Redis at {REDIS_URL} — start it with `docker compose up -d redis`",
)


@pytest.fixture
async def store():
    """A RedisStore on a unique key prefix, cleaned up afterwards.

    Every test uses a fresh random scope rather than FLUSHDB. The configured
    Redis may not be exclusively ours — on a hosted free tier it certainly is
    not — and a test suite that wipes a shared database is a trap waiting for
    whoever points REDIS_TEST_URL at the wrong thing.
    """
    store = RedisStore(REDIS_URL, fallback=MemoryStore())
    scope = f"test-{uuid.uuid4().hex}"
    yield store, scope

    client = store._connect()
    async for key in client.scan_iter(f"{KEY_PREFIX}{scope}*"):
        await client.delete(key)
    await store.close()


# --------------------------------------------------------------------------- #
# Against a real Redis
# --------------------------------------------------------------------------- #


@requires_redis
async def test_allows_up_to_the_limit(store) -> None:
    counter, scope = store
    for _ in range(5):
        assert await counter.hit(scope, limit=5, window_seconds=60) is None


@requires_redis
async def test_blocks_past_the_limit(store) -> None:
    counter, scope = store
    for _ in range(5):
        await counter.hit(scope, limit=5, window_seconds=60)

    retry_after = await counter.hit(scope, limit=5, window_seconds=60)
    assert retry_after is not None
    assert 0 < retry_after <= 60


@requires_redis
async def test_same_millisecond_hits_are_all_counted(store) -> None:
    """The reason each entry gets a random member rather than its timestamp.

    A sorted set holds each member once. With the timestamp as the member, two
    hits landing in the same millisecond would collapse into one entry and the
    limit would silently allow more than it says — under exactly the concurrency
    a shared counter exists to handle.

    Twenty concurrent hits against a limit of five: fifteen must be refused.
    """
    counter, scope = store
    results = await asyncio.gather(
        *(counter.hit(scope, limit=5, window_seconds=60) for _ in range(20))
    )
    assert sum(r is None for r in results) == 5


@requires_redis
async def test_two_stores_share_one_counter(store) -> None:
    """The whole point. Two workers, one budget.

    With per-process counters each of these would get its own five attempts and
    the effective limit would be ten.
    """
    counter, scope = store
    other = RedisStore(REDIS_URL, fallback=MemoryStore())
    try:
        for _ in range(3):
            assert await counter.hit(scope, limit=5, window_seconds=60) is None
        for _ in range(2):
            assert await other.hit(scope, limit=5, window_seconds=60) is None

        assert await other.hit(scope, limit=5, window_seconds=60) is not None
    finally:
        await other.close()


@requires_redis
async def test_peek_does_not_consume_budget(store) -> None:
    counter, scope = store
    await counter.hit(scope, limit=2, window_seconds=60)

    for _ in range(10):
        assert await counter.peek(scope, limit=2, window_seconds=60) is None

    assert await counter.hit(scope, limit=2, window_seconds=60) is None
    assert await counter.hit(scope, limit=2, window_seconds=60) is not None


@requires_redis
async def test_reset_clears_a_key(store) -> None:
    counter, scope = store
    for _ in range(3):
        await counter.hit(scope, limit=3, window_seconds=60)
    assert await counter.hit(scope, limit=3, window_seconds=60) is not None

    await counter.reset(scope)
    assert await counter.hit(scope, limit=3, window_seconds=60) is None


@requires_redis
async def test_window_slides(store) -> None:
    """Attempts age out, so a limit is a rate and not a lifetime cap."""
    counter, scope = store
    for _ in range(3):
        await counter.hit(scope, limit=3, window_seconds=0.4)
    assert await counter.hit(scope, limit=3, window_seconds=0.4) is not None

    await asyncio.sleep(0.5)
    assert await counter.hit(scope, limit=3, window_seconds=0.4) is None


@requires_redis
async def test_keys_expire(store) -> None:
    """Without PEXPIRE, every address that ever touched /login stays forever.

    A slow leak rather than a bug: nothing breaks, memory just grows without
    bound until the instance is full.
    """
    counter, scope = store
    await counter.hit(scope, limit=5, window_seconds=60)

    ttl = await counter._connect().pttl(KEY_PREFIX + scope)
    assert 0 < ttl <= 60_000


@requires_redis
async def test_get_store_returns_redis_when_configured(monkeypatch) -> None:
    """The selector, which is the part that decides whether any of this runs."""
    from app.core.config import get_settings

    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    get_settings.cache_clear()
    try:
        assert isinstance(get_store(), RedisStore)
    finally:
        monkeypatch.delenv("REDIS_URL", raising=False)
        get_settings.cache_clear()


def test_get_store_returns_memory_when_unset(monkeypatch) -> None:
    """No REDIS_URL means no Redis, and no dependency on one being reachable."""
    from app.core.config import get_settings

    monkeypatch.setenv("REDIS_URL", "")
    get_settings.cache_clear()
    try:
        assert isinstance(get_store(), MemoryStore)
    finally:
        monkeypatch.delenv("REDIS_URL", raising=False)
        get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# When Redis is not there
#
# No server needed: the URL points somewhere nothing is listening.
# --------------------------------------------------------------------------- #

DEAD = "redis://127.0.0.1:6390/0"


async def test_outage_falls_back_to_local_counting() -> None:
    """A dead Redis must not switch rate limiting off.

    Failing open turns an outage into the window an attacker was waiting for.
    Falling back to per-process counting keeps the door shut, just less tightly.
    """
    counter = RedisStore(DEAD, fallback=MemoryStore())
    try:
        for _ in range(3):
            assert await counter.hit("k", limit=3, window_seconds=60) is None
        assert await counter.hit("k", limit=3, window_seconds=60) is not None
    finally:
        await counter.close()


async def test_outage_does_not_raise() -> None:
    """The other half: a request must still be served.

    Failing closed would mean a dead cache locks every user out of their own
    account — the same outage, with worse consequences.
    """
    counter = RedisStore(DEAD, fallback=MemoryStore())
    try:
        assert await counter.peek("k", limit=3, window_seconds=60) is None
        await counter.reset("k")
    finally:
        await counter.close()


async def test_outage_is_logged_once(caplog) -> None:
    """Loudly, and then quietly.

    An outage under load would otherwise write one line per request and bury
    every other message in the log. The first line is the one that matters.
    """
    counter = RedisStore(DEAD, fallback=MemoryStore())
    try:
        with caplog.at_level("ERROR", logger="app.core.rate_limit_store"):
            for _ in range(5):
                await counter.hit("k", limit=100, window_seconds=60)
    finally:
        await counter.close()

    assert len(caplog.records) == 1
    assert "per-process" in caplog.records[0].message


@requires_redis
async def test_recovery_re_arms_the_warning(store, caplog) -> None:
    """One line per outage, not one per process lifetime.

    Every call still tries Redis, so recovery is automatic. But if the flag
    latched on the first failure ever seen, the *second* outage a long-lived
    worker lives through would pass in complete silence.
    """
    counter, scope = store
    counter._warned = True  # as if an outage had just been reported

    with caplog.at_level("INFO", logger="app.core.rate_limit_store"):
        await counter.hit(scope, limit=5, window_seconds=60)

    assert counter._warned is False
    assert any("answering again" in record.message for record in caplog.records)


async def test_reset_forgives_failures_recorded_during_an_outage() -> None:
    """A successful login has to clear both counters.

    Otherwise failures recorded locally while Redis was down survive its return,
    and the user stays locked out of an account they just proved they own.
    """
    fallback = MemoryStore()
    counter = RedisStore(DEAD, fallback=fallback)
    try:
        for _ in range(3):
            await counter.hit("k", limit=3, window_seconds=60)
        assert await fallback.peek("k", limit=3, window_seconds=60) is not None

        await counter.reset("k")
        assert await fallback.peek("k", limit=3, window_seconds=60) is None
    finally:
        await counter.close()
