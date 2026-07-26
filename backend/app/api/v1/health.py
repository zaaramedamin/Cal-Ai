"""Health check — the endpoint that proves the whole pipe works."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.db.session import get_session
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and database reachability",
)
async def health(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    """Report whether the API is up and whether it can actually reach Postgres.

    The database round-trip is the point. A health check that returns a constant
    string only proves the Python process is running — it would have reported
    "ok" all through Phase 0 while the database was never configured at all.
    `SELECT 1` is the cheapest query that proves a real connection, real
    credentials and a real network path.

    Why this returns HTTP 200 even when degraded: the mobile app needs to tell
    "the server is unreachable" (a network error, no response at all) apart from
    "the server is up but its database is down". A 503 collapses both into the
    same generic failure and the app can no longer show the user a useful
    message. When we deploy in Phase 7 and a load balancer becomes a consumer,
    that's when a separate `/health/ready` that *does* fail with 503 earns its
    place — a different consumer with genuinely different needs.
    """
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        # OSError as well as SQLAlchemyError: a refused TCP connection surfaces
        # as ConnectionRefusedError from asyncpg before SQLAlchemy wraps it.
        logger.warning("Health check could not reach the database: %s", exc)
        return HealthResponse(status="degraded", version=__version__, db="unreachable")

    return HealthResponse(status="ok", version=__version__, db="ok")
