"""Alembic migration environment.

A migration is a versioned, ordered script that transforms the database schema
from one state to the next. Every schema change from here on is a file in
`alembic/versions/` that is committed alongside the code that needs it — which
means the database can be rebuilt from scratch, the change is reviewable in a
pull request, and there is a defined way back. Editing the schema by hand in a
GUI leaves no record and no way to reproduce it on another machine.

Two deliberate departures from the template Alembic generates:

1. The database URL comes from `app.core.config.Settings`, not `alembic.ini`, so
   there is exactly one place a connection string is defined.
2. The engine is built directly rather than via `async_engine_from_config`. That
   function reads through configparser, which treats `%` as interpolation syntax
   — a password containing `%` would blow up with a confusing parse error.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Importing the models package registers every table on Base.metadata before
# autogenerate compares it against the live database. Without this import,
# autogenerate sees no tables and cheerfully generates a migration that drops
# every table it cannot account for.
import app.db.models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade head --sql`).

    Useful when a production database is managed by someone who wants to review
    and apply the SQL themselves.
    """
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Notice column type changes (e.g. numeric(5,1) -> numeric(6,2)), which
        # Alembic ignores by default. For an app where every stored number is a
        # nutrition value, a silently missed precision change is a real bug.
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        settings.database_url,
        # NullPool: migrations are a short-lived one-shot process. Pooling would
        # only leave connections open after the work is done.
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
