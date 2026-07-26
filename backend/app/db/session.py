"""Async engine and per-request session.

A "session" is SQLAlchemy's unit of work: it holds the objects you've read or
changed and writes them out as one transaction. One session per HTTP request is
the standard shape — the request either commits as a whole or rolls back as a
whole, and two concurrent requests can never see each other's uncommitted rows.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    # Verify a pooled connection is still alive before handing it out. We are
    # literally going to run `docker compose stop` as a Phase 0 test, which kills
    # every pooled connection. Without pre-ping, the first request after the
    # database comes back fails on a dead socket even though the database is fine.
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    # With the default (True), reading any attribute after commit triggers a
    # silent reload from the database. Under asyncio that lazy IO happens outside
    # an await and raises MissingGreenlet — a genuinely baffling error. Turning it
    # off means committed objects stay usable, which is what you expect anyway.
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency yielding one session per request.

    Note the session opens no connection until the first query runs. That is what
    lets the health endpoint catch an unreachable database inside the handler
    rather than blowing up here in the dependency.
    """
    async with SessionFactory() as session:
        yield session
