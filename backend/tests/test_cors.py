"""CORS, and the fact that its default is a decision rather than an omission.

The only client is a native app, and React Native ignores CORS entirely — so an
API that sends no CORS headers is fully functional for every real user while
being unreadable to a browser on another origin. That is the correct default, and
these tests exist so nobody "fixes" it back to `*` on the way to shipping the web
target.
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

ORIGIN = "https://evil.example.com"
ALLOWED = "https://app.calai.com"


@pytest.fixture
def env() -> Iterator[None]:
    """Restore ENVIRONMENT and CORS_ORIGINS, and the settings cache, after each test."""
    previous = {key: os.environ.get(key) for key in ("ENVIRONMENT", "CORS_ORIGINS")}
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()


def _preflight(origin: str) -> object:
    client = TestClient(create_app())
    return client.options(
        "/api/v1/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )


def test_development_allows_any_origin(env):
    """Convenience while developing, where the alternative is a daily annoyance."""
    os.environ["ENVIRONMENT"] = "development"
    get_settings.cache_clear()

    response = _preflight(ORIGIN)
    assert response.headers.get("access-control-allow-origin") == "*"


def test_production_sends_no_cors_headers_by_default(env):
    """The important one.

    An unconfigured production deployment must not hand a browser permission to
    read authenticated responses. No header means the browser refuses, which is
    exactly right when every real client is a native app.
    """
    os.environ["ENVIRONMENT"] = "production"
    os.environ.pop("CORS_ORIGINS", None)
    get_settings.cache_clear()

    response = _preflight(ORIGIN)
    assert "access-control-allow-origin" not in response.headers


def test_production_allows_only_the_named_origins(env):
    os.environ["ENVIRONMENT"] = "production"
    os.environ["CORS_ORIGINS"] = f"{ALLOWED},https://calai.com"
    get_settings.cache_clear()

    allowed = _preflight(ALLOWED)
    assert allowed.headers.get("access-control-allow-origin") == ALLOWED

    refused = _preflight(ORIGIN)
    assert refused.headers.get("access-control-allow-origin") != ORIGIN


def test_a_comma_separated_env_var_is_parsed(env):
    """`CORS_ORIGINS=a,b` is how an env var is written.

    Without the validator pydantic tries to JSON-decode a `list[str]` and fails
    at startup with an error naming neither the variable nor the format.
    """
    os.environ["ENVIRONMENT"] = "production"
    os.environ["CORS_ORIGINS"] = " https://a.com , https://b.com "
    get_settings.cache_clear()

    assert get_settings().cors_origins == ["https://a.com", "https://b.com"]
