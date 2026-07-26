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
# would make these tests pass or fail depending on someone's local machine.
NO_ENV_FILE: dict[str, None] = {"_env_file": None}


def test_accepts_async_driver_url() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://calai:pw@localhost:5432/calai",
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
        Settings(database_url=url, **NO_ENV_FILE)


def test_missing_database_url_fails_loudly() -> None:
    """A missing required variable must fail at construction, not return None."""
    with pytest.raises(ValidationError):
        Settings(**NO_ENV_FILE)


def test_is_development_tracks_environment() -> None:
    url = "postgresql+asyncpg://calai:pw@localhost:5432/calai"
    assert Settings(database_url=url, environment="development", **NO_ENV_FILE).is_development
    assert not Settings(database_url=url, environment="production", **NO_ENV_FILE).is_development
