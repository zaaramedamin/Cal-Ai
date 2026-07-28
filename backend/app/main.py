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
from pymongo.errors import PyMongoError
from sqlalchemy.exc import DBAPIError

from app import __version__
from app.api.v1 import api_router
from app.core.config import get_settings
from app.db.mongo import close_client, ensure_indexes
from app.db.session import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup and shutdown.

    Postgres is left alone on startup: the engine connects lazily, so eagerly
    opening a pool here would only mean the API refuses to boot when Postgres
    happens to be down — exactly the situation the health endpoint exists to
    report on.

    Mongo needs one piece of eager work, because it has no migrations: its
    indexes have to be created *somewhere*, and doing it here means a fresh clone
    gets a correct database from `docker compose up` with no separate setup step
    to forget. It is idempotent and costs a few milliseconds.

    A failure is logged and swallowed, on the same principle as Postgres. Half
    this app — auth, the diary, progress — does not touch Mongo at all, and
    refusing to serve any of it because an index could not be created would turn
    a degraded dependency into a total outage.
    """
    try:
        await ensure_indexes()
    except PyMongoError as exc:
        logger.warning("Could not create MongoDB indexes at startup: %s", exc)

    yield

    await engine.dispose()
    await close_client()


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
    # ignores it entirely, so this does nothing for Expo Go on your phone. It
    # matters for Expo's web target and for the /docs page. Wide open in
    # development only; Phase 7 must set an explicit origin list before deploying.
    if settings.is_development:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Both types are needed, and finding that out took a live test. asyncpg
    # raises a bare OSError (`ConnectionRefusedError`) when it cannot reach the
    # server at all — the connect fails before SQLAlchemy has anything to wrap.
    # `DBAPIError` covers the other half: a pooled connection that dies mid-use,
    # or the pre-ping failing on a stale socket. Registering only the SQLAlchemy
    # one, which is the obvious guess, catches neither of the common cases.
    @app.exception_handler(DBAPIError)
    @app.exception_handler(ConnectionRefusedError)
    async def _database_unreachable(request: Request, exc: Exception) -> JSONResponse:
        """Turn a dead database into an answer instead of a shrug.

        Without this, stopping Postgres and leaving the API running produces the
        least useful failure the app can show. The exception is unhandled, so
        Starlette answers with a **plain-text** 500 — and the client parses error
        bodies as JSON to read FastAPI's `detail`, finds nothing, and falls back
        to its generic "something went wrong on the server". The one machine that
        knows exactly what is wrong says the least about it.

        This project makes that easy to hit: the database is a container you are
        told to start separately, so restarting the API without it is a normal
        Tuesday. A JSON 503 naming the fix costs nothing and turns a debugging
        session into a single command.

        Scoped to `DBAPIError` (connection and driver failures) rather than
        `SQLAlchemyError`, which would also swallow genuine programming errors
        like a bad query and report them as infrastructure problems.
        """
        logger.error("Database unreachable on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": (
                    "The database isn't reachable. If you're running locally, start it with "
                    "`docker compose up -d` and try again."
                )
            },
        )

    @app.exception_handler(PyMongoError)
    async def _mongo_unreachable(request: Request, exc: Exception) -> JSONResponse:
        """The same courtesy for the other database.

        Mongo fails differently from Postgres and would otherwise produce the
        same useless plain-text 500: the driver waits out its five-second server
        selection timeout and raises, the client cannot parse the body, and the
        user gets "something went wrong on the server" while the one machine that
        knows the answer says nothing.

        Catching `PyMongoError` broadly is deliberate here, unlike the narrow
        `DBAPIError` above. There is no equivalent of a "bad query" mistake to
        confuse it with: nothing in this codebase builds Mongo queries from user
        input, so in practice every error reaching this point is the connection.
        """
        logger.error("MongoDB unreachable on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": (
                    "The food catalogue database isn't reachable. If you're running "
                    "locally, start it with `docker compose up -d` and try again."
                )
            },
        )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
