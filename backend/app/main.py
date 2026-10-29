"""Application entry point.

Run in development with:

    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

`--host 0.0.0.0` is not optional when testing on a phone. The default binds to
127.0.0.1, which accepts connections originating from this machine only — the
phone's requests are refused before they reach any of this code.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from app import __version__
from app.admin.router import router as admin_router
from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.rate_limit_store import close_store
from app.core.tls import use_system_trust_store
from app.db.session import engine

logger = logging.getLogger(__name__)

# At import time, before anything builds an SSL context. See `core/tls.py` — on a
# machine where antivirus or a VPN re-signs HTTPS, certifi cannot verify anything
# and every USDA and Gemini call fails in a way that looks like the upstream
# service being down.
use_system_trust_store()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup and shutdown.

    Nothing eager happens on startup. The engine connects lazily, so opening a
    pool here would only mean the API refuses to boot when Postgres happens to be
    down — exactly the situation the health endpoint exists to report on.

    There used to be index creation here, because MongoDB has no migrations and
    they had to be built *somewhere*. Alembic owns that now, which is the point:
    schema changes belong in a reviewed, ordered, reversible migration rather
    than in a startup hook that runs on every boot and can only add.

    Shutdown closes the Redis connection used for rate limiting, if one was ever
    opened. It is built lazily, so on a deployment without REDIS_URL this is a
    no-op.
    """
    yield

    await engine.dispose()
    await close_store()


def create_app() -> FastAPI:
    """Build the app.

    A factory rather than a module-level `app = FastAPI()` because tests need to
    construct an app with overridden settings. Wiring that happens inside a
    function can be repeated; wiring that happens at import time cannot.
    """
    settings = get_settings()

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s  %(levelname)-8s %(name)s  %(message)s",
    )

    app = FastAPI(
        title="CalAi API",
        version=__version__,
        summary="Calorie and macronutrient tracking.",
        # Served under the version prefix because this schema is the contract the
        # mobile app's TypeScript client is generated from — it is versioned data,
        # not a static asset.
        openapi_url="/api/v1/openapi.json",
        docs_url="/docs" if settings.is_development else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # CORS is a *browser* mechanism: React Native issues native HTTP requests and
    # ignores it entirely, so none of this affects Expo Go on a phone. It matters
    # for Expo's web target and for the /docs page.
    #
    # Development stays wide open. Production sends no CORS headers at all unless
    # CORS_ORIGINS names the origins explicitly — an empty list means no browser
    # on another origin can read a response, which is the right default for an
    # API whose only client is a native app. Deploying the web target is what
    # makes setting it necessary, and at that point the value is known.
    #
    # `allow_credentials` follows the origin list rather than being hardcoded:
    # the browser refuses `allow_credentials` together with `*` anyway, and this
    # app authenticates with a bearer token rather than a cookie, so credentials
    # are only meaningful once real origins are named.
    origins = ["*"] if settings.is_development else settings.cors_origins
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=not settings.is_development,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Which exceptions mean "the database is unreachable" — and, just as
    # importantly, which do not.
    #
    # `ConnectionRefusedError` is a bare OSError from asyncpg when it cannot
    # reach the server at all; the connect fails before SQLAlchemy has anything
    # to wrap. `OperationalError` and `InterfaceError` cover the other half: a
    # pooled connection dying mid-use, or a pre-ping failing on a stale socket.
    #
    # **This used to catch `DBAPIError`, and that was a real bug.** The docstring
    # claimed the narrower scope kept "genuine programming errors like a bad
    # query" out — but `ProgrammingError`, `IntegrityError` and `DataError` are
    # all DBAPIError subclasses, so it caught exactly what it said it excluded.
    # It cost two debugging sessions in one day: a missing migration reported as
    # "start the database", and a unique-constraint violation reported the same
    # way while the database was plainly fine. A constraint violation is a bug in
    # this code; saying "the database isn't reachable" sends whoever reads it to
    # the wrong machine entirely.
    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    @app.exception_handler(ConnectionRefusedError)
    async def _database_unreachable(request: Request, exc: Exception) -> JSONResponse:
        """Turn a dead database into an answer instead of a shrug.

        Without this, stopping Postgres and leaving the API running produces the
        least useful failure the app can show. The exception is unhandled, so
        Starlette answers with a **plain-text** 500 — and the client parses error
        bodies as JSON to read FastAPI's `detail`, finds nothing, and falls back
        to its generic "something went wrong on the server". The one machine that
        knows exactly what is wrong says the least about it.

        The message names both places the database can be, because both are
        real: Supabase for the app, and the local container that the test suite
        and an offline laptop use. Naming only the container sent people to start
        Docker while `DATABASE_URL` pointed at Supabase all along.
        """
        logger.error("Database unreachable on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": (
                    "The database isn't reachable. Check the host in DATABASE_URL: for "
                    "Supabase, that the project is not paused; for the local container, "
                    "start it with `docker compose up -d`."
                )
            },
        )

    app.include_router(api_router, prefix="/api/v1")

    # The admin console. Mounted outside the versioned prefix on purpose: it is
    # a page, not part of the contract the mobile client is generated from, and
    # it holds no privileges of its own — it signs in as an ordinary admin and
    # calls the same endpoints the phone does. See app/admin/__init__.py.
    app.include_router(admin_router)

    return app


app = create_app()
