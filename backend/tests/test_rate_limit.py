"""Rate limiting.

Split in two: unit tests of the counter, where time can be controlled precisely,
and endpoint tests proving the limits are actually wired up. The second kind is
what catches a limit that exists but was never attached to a route.

The Redis-backed counter is tested separately, in `test_rate_limit_redis.py` —
it needs a server, and these must not.
"""

import time

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import (
    LOGIN_ACCOUNT_MAX_ATTEMPTS,
    LOGIN_ACCOUNT_WINDOW_SECONDS,
    clear_failures,
    is_blocked,
    record_failure,
)
from app.core.rate_limit_store import MemoryStore

# --------------------------------------------------------------------------- #
# The counter
# --------------------------------------------------------------------------- #


async def test_allows_up_to_the_limit() -> None:
    counter = MemoryStore()
    for _ in range(5):
        assert await counter.hit("k", limit=5, window_seconds=60) is None


async def test_blocks_past_the_limit() -> None:
    counter = MemoryStore()
    for _ in range(5):
        await counter.hit("k", limit=5, window_seconds=60)

    retry_after = await counter.hit("k", limit=5, window_seconds=60)
    assert retry_after is not None
    assert 0 < retry_after <= 60


async def test_keys_are_independent() -> None:
    """One address hitting its limit must not lock everyone else out."""
    counter = MemoryStore()
    for _ in range(5):
        await counter.hit("attacker", limit=5, window_seconds=60)

    assert await counter.hit("attacker", limit=5, window_seconds=60) is not None
    assert await counter.hit("someone-else", limit=5, window_seconds=60) is None


async def test_window_slides() -> None:
    """Attempts age out, so a limit is a rate and not a lifetime cap."""
    counter = MemoryStore()
    for _ in range(3):
        await counter.hit("k", limit=3, window_seconds=0.15)
    assert await counter.hit("k", limit=3, window_seconds=0.15) is not None

    time.sleep(0.2)
    assert await counter.hit("k", limit=3, window_seconds=0.15) is None


async def test_sliding_window_has_no_boundary_burst() -> None:
    """The reason this is a log rather than a fixed-window counter.

    A fixed window resets on a calendar boundary, letting an attacker send the
    full budget just before it and again just after — twice the intended rate.
    Here the oldest attempt has to genuinely age out.
    """
    counter = MemoryStore()
    for _ in range(3):
        await counter.hit("k", limit=3, window_seconds=0.3)

    time.sleep(0.15)  # half the window
    assert await counter.hit("k", limit=3, window_seconds=0.3) is not None


async def test_peek_does_not_consume_budget() -> None:
    """Checking whether a key is blocked must not itself block it."""
    counter = MemoryStore()
    await counter.hit("k", limit=2, window_seconds=60)

    for _ in range(10):
        assert await counter.peek("k", limit=2, window_seconds=60) is None

    assert await counter.hit("k", limit=2, window_seconds=60) is None
    assert await counter.hit("k", limit=2, window_seconds=60) is not None


async def test_reset_clears_a_key() -> None:
    counter = MemoryStore()
    for _ in range(3):
        await counter.hit("k", limit=3, window_seconds=60)
    assert await counter.hit("k", limit=3, window_seconds=60) is not None

    await counter.reset("k")
    assert await counter.hit("k", limit=3, window_seconds=60) is None


# --------------------------------------------------------------------------- #
# Wired up to the endpoints
# --------------------------------------------------------------------------- #

PASSWORD = "correct-horse-battery"


@pytest.mark.usefixtures("rate_limited")
def test_login_blocks_repeated_failures(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register", json={"email": "target@example.com", "password": PASSWORD}
    )

    statuses = [
        client.post(
            "/api/v1/auth/login",
            json={"email": "target@example.com", "password": "wrong-every-time"},
        ).status_code
        for _ in range(12)
    ]

    assert 401 in statuses, "early attempts should be ordinary credential failures"
    assert 429 in statuses, "an unlimited login endpoint is a credential-stuffing surface"


@pytest.mark.usefixtures("rate_limited")
def test_rate_limited_response_says_how_long_to_wait(client: TestClient) -> None:
    """RFC 6585 requires Retry-After on 429, and the app shows it to the user
    instead of letting them hammer a dead button."""
    for _ in range(12):
        response = client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "guessing"}
        )
        if response.status_code == 429:
            assert int(response.headers["Retry-After"]) > 0
            return

    pytest.fail("login was never rate limited")


@pytest.mark.usefixtures("rate_limited")
async def test_successful_login_clears_the_account_counter() -> None:
    """Limits punish failure, not use.

    Without the reset, someone who mistypes a few times and then signs in
    successfully still carries those strikes, and a later genuine slip locks them
    out of their own account.

    Tested against the counter directly rather than over HTTP on purpose. Driving
    it through the endpoint needs more requests than the *per-IP* budget allows,
    so the IP limiter would fire first and the test would pass or fail for a
    reason unrelated to what it claims to check.
    """
    account = "forgetful@example.com"
    limits = {"times": LOGIN_ACCOUNT_MAX_ATTEMPTS, "seconds": LOGIN_ACCOUNT_WINDOW_SECONDS}

    for _ in range(LOGIN_ACCOUNT_MAX_ATTEMPTS):
        await record_failure("login-account", account, **limits)
    assert await is_blocked("login-account", account, **limits) is not None

    await clear_failures("login-account", account)
    assert await is_blocked("login-account", account, **limits) is None


@pytest.mark.usefixtures("rate_limited")
async def test_account_limit_is_case_insensitive() -> None:
    """Emails are case-insensitive in the database, so the counter must match.

    Otherwise an attacker cycles Target@x.com, TARGET@x.com, tArGeT@x.com and
    gets a fresh budget for each spelling of one account.
    """
    limits = {"times": LOGIN_ACCOUNT_MAX_ATTEMPTS, "seconds": LOGIN_ACCOUNT_WINDOW_SECONDS}

    for _ in range(LOGIN_ACCOUNT_MAX_ATTEMPTS):
        await record_failure("login-account", "Target@Example.com", **limits)

    assert await is_blocked("login-account", "target@example.com", **limits) is not None


@pytest.mark.usefixtures("rate_limited")
def test_password_reset_requests_are_limited(client: TestClient) -> None:
    """Each request sends an email, so an unlimited endpoint is a way to use our
    server to spam somebody else's inbox."""
    statuses = [
        client.post(
            "/api/v1/auth/password-reset/request", json={"email": "victim@example.com"}
        ).status_code
        for _ in range(8)
    ]
    assert 429 in statuses


@pytest.mark.usefixtures("rate_limited")
def test_reset_request_and_confirm_have_separate_budgets(client: TestClient) -> None:
    """Regression test for a real bug found in end-to-end testing.

    When both endpoints shared one scope, a user would request a link (one hit),
    then mistype their new password a few times — and each rejected submission
    burned the same budget, locking them out of finishing their own reset.

    Here: exhaust the request budget entirely, then confirm that submitting the
    form still gets a real answer (400 for a bad token) rather than a 429.
    """
    for _ in range(8):
        client.post("/api/v1/auth/password-reset/request", json={"email": "someone@example.com"})

    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "not-a-real-token", "new_password": "a-long-enough-password"},
    )
    assert response.status_code == 400, "confirm must not share the request endpoint's budget"


def test_limits_are_disabled_in_the_rest_of_the_suite(client: TestClient) -> None:
    """Guards the fixture itself.

    If RATE_LIMIT_ENABLED ever stopped being applied, the other auth tests would
    start failing with 429s that look like credential bugs. Better to fail here,
    where the message says what actually happened.
    """
    statuses = [
        client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
        ).status_code
        for _ in range(15)
    ]
    assert 429 not in statuses
