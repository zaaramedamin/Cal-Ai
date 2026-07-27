"""Settings validation.

These are cheap tests of an expensive mistake. The async-driver check is the kind
of rule that silently stops being enforced when someone "simplifies" the
validator away, and the failure it prevents — a blocking driver stalling the
event loop — only shows up under concurrency, long after the change.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

# _env_file=None stops pydantic-settings reading the developer's real .env, which
# would make these tests pass or fail depending on someone's local machine. Every
# required field therefore has to be supplied explicitly.
NO_ENV_FILE: dict[str, None] = {"_env_file": None}
VALID_SECRET = "x" * 64


def test_accepts_async_driver_url() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://calai:pw@localhost:5432/calai",
        secret_key=VALID_SECRET,
        **NO_ENV_FILE,
    )
    assert settings.database_url.startswith("postgresql+asyncpg://")


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://calai:pw@localhost:5432/calai",  # sync psycopg driver
        "postgres://calai:pw@localhost:5432/calai",  # the old scheme alias
        "sqlite+aiosqlite:///./calai.db",  # right idea, wrong database
        "",
    ],
)
def test_rejects_non_asyncpg_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(database_url=url, secret_key=VALID_SECRET, **NO_ENV_FILE)


def test_missing_database_url_fails_loudly() -> None:
    """A missing required variable must fail at construction, not return None."""
    with pytest.raises(ValidationError):
        Settings(**NO_ENV_FILE)


def test_is_development_tracks_environment() -> None:
    url = "postgresql+asyncpg://calai:pw@localhost:5432/calai"
    common = {"database_url": url, "secret_key": VALID_SECRET, **NO_ENV_FILE}
    assert Settings(environment="development", **common).is_development
    assert not Settings(environment="production", **common).is_development


@pytest.mark.parametrize(
    "secret",
    [
        "replace-me-with-a-64-byte-random-string",  # the committed placeholder
        "short",
        "",
    ],
)
def test_rejects_weak_or_placeholder_secret_key(secret: str) -> None:
    """Shipping with the .env.example value would let anyone who read the repo
    forge a token for any account. Refusing to boot is the right response."""
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+asyncpg://calai:pw@localhost:5432/calai",
            secret_key=secret,
            **NO_ENV_FILE,
        )
