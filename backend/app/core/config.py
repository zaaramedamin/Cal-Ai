"""Application settings.

Everything environment-specific enters the app through this one module. Nothing
else in the codebase reads `os.environ`, so there is exactly one place to look
when you need to know what the app can be configured with.

Why `pydantic-settings` rather than reading `os.environ` directly:

* Environment variables are always strings. `Settings` declares real types, so
  `ACCESS_TOKEN_EXPIRE_MINUTES` arrives as an `int` and a typo like `"fifteen"`
  is a startup error instead of a `TypeError` deep inside a request.
* A missing required variable fails immediately at import, with a message naming
  the variable. The alternative — `os.environ.get("DATABASE_URL")` returning
  `None` — surfaces hours later as a confusing crash somewhere unrelated.
* It is self-documenting: this class is the authoritative list of every knob,
  and it is what `.env.example` is kept in sync with.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py -> core -> app -> backend -> repo root. Resolved from __file__ rather
# than the working directory, so uvicorn, alembic and pytest all find the same
# .env no matter which folder they were launched from.
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        # The .env also carries POSTGRES_* (consumed by docker-compose) and keys
        # for phases not yet built. Ignore rather than reject: one .env serving
        # both compose and the app is less to keep in sync than two.
        extra="ignore",
    )

    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    database_url: str

    # ---- Auth -------------------------------------------------------------
    # Signs access tokens. Rotating it invalidates every issued token at once,
    # which is the intended panic button if one ever leaks.
    secret_key: str

    # Deliberately short. An access token cannot be revoked — anyone holding it
    # is authenticated until it expires, because verifying it involves no
    # database lookup at all (that is the whole point of a JWT). The only real
    # control over a stolen one is that it stops working quickly.
    access_token_expire_minutes: int = 15

    # Long, because this is what saves the user from logging in every 15 minutes.
    # Safe to be long *because* it is revocable: it lives in the database, and
    # logout deletes it.
    refresh_token_expire_days: int = 30

    # Short on purpose. A reset link sits in an inbox, which is a far less
    # trustworthy place than the device keystore — shared computers, forwarded
    # mail, a mailbox someone else already has access to. Thirty minutes is long
    # enough to walk to a laptop and short enough that a stale link is useless.
    password_reset_expire_minutes: int = 30

    # ---- Rate limiting ----------------------------------------------------
    # Switched off in tests, where dozens of deliberate login failures would
    # otherwise trip the limiter and make unrelated assertions fail.
    rate_limit_enabled: bool = True

    # Only enable behind a proxy that overwrites X-Forwarded-For (Railway, Fly,
    # a properly configured nginx). Trusting the header without one lets any
    # client forge its address and bypass every per-IP limit.
    trust_proxy_headers: bool = False

    # ---- Nutrition data sources -------------------------------------------
    # DEMO_KEY works but allows only 30 requests an hour, which the search screen
    # exhausts almost immediately. A real key is free.
    usda_api_key: str = "DEMO_KEY"
    off_user_agent: str = "CalAi/0.1 (contact@example.com)"

    # ---- AI meal scanning ---------------------------------------------------
    # Empty means the scan feature is disabled and its endpoint answers 503 with
    # instructions — unlike SECRET_KEY this must NOT prevent boot, because the
    # rest of the app works fine without it. Free key: aistudio.google.com/apikey
    gemini_api_key: str = ""

    # Flash-*lite*, and the "lite" is the whole point on a free tier.
    #
    # An alias rather than a pinned version, because Google retires pinned models
    # for new API keys while leaving them listed — `gemini-2.5-flash` worked for
    # months and then 404'd for a key issued today. But the alias has its own
    # trap: `gemini-flash-latest` now resolves to gemini-3.6-flash, whose free
    # tier is **20 requests per day**. That is not a scanning feature, it is a
    # demo. Flash-lite carries a far larger free allowance and identifies food
    # from a photo perfectly well — this is recognition, not reasoning.
    #
    # Set GEMINI_MODEL to `gemini-flash-latest` for the stronger model if you
    # ever move to a paid key, where the daily cap stops mattering.
    gemini_model: str = "gemini-flash-lite-latest"

    @field_validator("secret_key")
    @classmethod
    def _reject_placeholder_secret(cls, value: str) -> str:
        """Refuse to start on the committed placeholder or an obviously weak key.

        The failure this prevents is quiet and serious: shipping with the
        .env.example value means anyone who has read the repo can forge tokens
        for any user. A crash on boot is a good trade for that.
        """
        if "replace-me" in value or len(value) < 32:
            raise ValueError(
                "SECRET_KEY must be a real random value of at least 32 characters. "
                'Generate one with: python -c "import secrets; '
                "print(secrets.token_urlsafe(64))\""
            )
        return value

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, value: str) -> str:
        """Reject a sync driver loudly instead of silently blocking the loop.

        FastAPI serves requests on a single event loop. A synchronous driver
        (`postgresql://` → psycopg) blocks that loop for the whole query, so
        every other in-flight request stalls behind it. The app would still
        "work" in local testing with one user and fall over under any real
        concurrency — the worst kind of bug. Failing at startup is cheaper.
        """
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use the async driver, e.g. "
                "postgresql+asyncpg://user:pass@localhost:5432/calai — "
                f"got {value.split('://', 1)[0]!r}"
            )
        return value

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings.

    Cached because reading and validating the .env on every request would be
    pure waste, and because a single instance means configuration cannot drift
    between two parts of the app mid-run.
    """
    return Settings()
