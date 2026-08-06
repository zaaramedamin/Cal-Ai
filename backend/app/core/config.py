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
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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

    #: Where the test suite is allowed to run. Test-only, and listed here because
    #: this class is the one place environment variables are read.
    #:
    #: It exists because the fixtures CREATE a database and TRUNCATE tables
    #: between every test, and they used to derive their target from
    #: `database_url`. That was harmless while that pointed at a local container
    #: and became a live hazard the moment it pointed at Supabase — a single line
    #: edited in `.env` would have aimed the suite at production. `conftest.py`
    #: refuses to run against a host it does not recognise as local unless this
    #: is set explicitly.
    test_database_url: str | None = None

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

    #: Serve the admin console at `/admin`.
    #:
    #: On by default because a review queue nobody can action is a queue that
    #: fills up. Turning it off removes the page only — the admin API is
    #: unchanged, and it already answers 404 to non-admins, so this is about not
    #: advertising that the surface exists rather than about access control.
    admin_ui_enabled: bool = True

    #: Where rate-limit counters live. Empty means the memory of one process.
    #:
    #: That default is correct for local development and wrong the moment more
    #: than one worker serves traffic: each keeps its own tally, so a limit of
    #: ten becomes ten *per worker*, and a restart forgives every attacker
    #: mid-attack. Setting this points every worker at one shared counter.
    #:
    #: e.g. redis://127.0.0.1:6379/0, or rediss://…@….upstash.io:6379 hosted.
    redis_url: str = ""

    # ---- Supabase Auth ------------------------------------------------------
    #: The project URL, e.g. https://abcdefgh.supabase.co
    #:
    #: Empty means Supabase Auth is switched off and the hand-built auth is
    #: still in charge — the two can coexist during the migration, and a missing
    #: value must not stop the app booting.
    supabase_url: str = ""

    #: The publishable ("anon") key. **Not a secret**: it is compiled into the
    #: mobile app, and Supabase's model assumes an attacker holds it. Access is
    #: controlled by row-level security and by token verification, never by
    #: keeping this hidden. It is here because the backend needs it to call the
    #: auth API on a user's behalf, not to protect anything.
    supabase_anon_key: str = ""

    @property
    def supabase_auth_enabled(self) -> bool:
        return bool(self.supabase_url)

    @property
    def supabase_jwks_url(self) -> str:
        """Where the public signing keys live.

        Derived rather than configured. It is fixed by Supabase's URL scheme, so
        a separate setting would only be an opportunity to mistype it.
        """
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def supabase_issuer(self) -> str:
        """The `iss` claim every token from this project must carry."""
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    # ---- CORS ---------------------------------------------------------------
    #: Browser origins allowed to read responses, in production.
    #:
    #: Empty by default, and that default is deliberate rather than unfinished:
    #: the only client is a native app, which does not use CORS at all, so
    #: sending no headers denies every cross-origin browser read. Naming origins
    #: is what deploying the Expo web target requires, and by then the value is
    #: known — guessing it now would mean shipping a permission nobody needs.
    #:
    #: Set as a comma-separated list, e.g.
    #:   CORS_ORIGINS=https://app.calai.com,https://calai.com
    #:
    #: `NoDecode` is required, not decorative. pydantic-settings treats any
    #: `list[str]` as a complex field and JSON-decodes the environment value
    #: *before* field validators run — so `CORS_ORIGINS=a,b` fails at startup
    #: with a JSON error naming neither the variable nor the expected format.
    #: NoDecode hands the raw string to the validator below instead.
    cors_origins: Annotated[list[str], NoDecode] = []

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string, because that is what an env var is."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

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

    #: A second key, used for the text paths — meal descriptions and the
    #: nutrition-estimate fallback.
    #:
    #: **Why two keys rather than one.** The free tier is metered per key, so a
    #: second one both doubles the daily budget and, more usefully, isolates the
    #: two features from each other. With a single key, a user describing ten
    #: meals in an afternoon exhausts the quota that photo scanning needs — and
    #: photo scanning is the harder feature to replace, because a description can
    #: always be typed into search instead.
    #:
    #: Falls back to `gemini_api_key` when unset, so one key still works and
    #: nothing breaks by leaving this blank.
    gemini_text_api_key: str = ""

    @property
    def gemini_key_for_text(self) -> str:
        """The key the text paths should spend. Falls back to the photo key."""
        return self.gemini_text_api_key or self.gemini_api_key

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
                'print(secrets.token_urlsafe(64))"'
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
