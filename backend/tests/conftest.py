"""Test fixtures.

These tests run against a **real Postgres**, in a separate `calai_test` database
on the same container as development. That is deliberate, over the two easier
options:

* SQLite has no CITEXT, no native UUID type, and different transaction
  semantics. Passing tests would prove nothing about the database we ship on —
  and the case-insensitive email rule, a real correctness property, could not be
  tested at all.
* Mocking the session would verify that our code calls SQLAlchemy the way we
  expect, not that the resulting SQL is right. Auth bugs live in the second.

The schema is built by running the real Alembic migrations, so a migration that
does not actually work fails the suite here rather than on deploy.
"""

import os
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.rate_limit import reset_all
from app.db.mongo import FOOD_ITEMS, MEALS, close_client
from app.schemas.catalogue import CatalogueFood, Portion, UnitKind

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_NAME = "calai_test"
#: Same reasoning as the Postgres test database, and the same name for symmetry.
#: Mongo creates a database on first write, so nothing has to pre-create this.
TEST_MONGO_DB = "calai_test"


def _swap_database(url: str, database: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{database}"))


def _asyncpg_dsn(url: str) -> str:
    """Strip SQLAlchemy's `+asyncpg` marker so raw asyncpg accepts the DSN."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


TEST_DATABASE_URL = _swap_database(get_settings().database_url, TEST_DB_NAME)
ADMIN_DSN = _asyncpg_dsn(_swap_database(get_settings().database_url, "postgres"))


@pytest.fixture(scope="session", autouse=True)
def _prepare_database() -> Iterator[None]:
    """Create `calai_test` and bring it to the latest migration, once per run."""

    async def create_if_missing() -> None:
        conn = await asyncpg.connect(ADMIN_DSN)
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
            )
            if not exists:
                # CREATE DATABASE cannot run inside a transaction, and the name
                # cannot be parameterised — it is a constant defined above, not
                # user input, so interpolating it is safe here.
                await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
        finally:
            await conn.close()

    import asyncio

    asyncio.run(create_if_missing())

    # Point everything that reads Settings at the test database. The cache has to
    # be cleared because Settings is lru_cached and Alembic's env.py calls it.
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    previous_mongo = os.environ.get("MONGODB_DB")
    os.environ["MONGODB_DB"] = TEST_MONGO_DB

    # Rate limiting off by default. The auth tests make dozens of deliberate
    # failed logins, which would otherwise trip the limiter and fail assertions
    # about credentials with a 429 — a confusing failure in an unrelated test.
    # The tests that care switch it back on explicitly.
    os.environ["RATE_LIMIT_ENABLED"] = "false"
    get_settings.cache_clear()

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")

    yield

    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous
    if previous_mongo is None:
        os.environ.pop("MONGODB_DB", None)
    else:
        os.environ["MONGODB_DB"] = previous_mongo
    get_settings.cache_clear()


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    """A fresh engine per test, with pooling disabled.

    Both details are load-bearing. pytest-asyncio runs each test in its own event
    loop, and an asyncpg connection is bound to the loop that opened it. A
    session-scoped engine would pool connections from the first test's loop and
    hand them to the second, which fails with an opaque InterfaceError that looks
    like a database problem and is not.

    NullPool closes each connection when it is returned, so nothing survives to
    be reused across loops. Slower, and exactly right for tests.
    """
    eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables(engine) -> AsyncGenerator[None]:
    """Empty every table between tests.

    TRUNCATE ... CASCADE rather than dropping and recreating the schema: it is
    far faster, and it resets the tables without re-running migrations. Each test
    therefore starts from a known-empty database and cannot be affected by the
    order tests happen to run in.
    """
    yield
    reset_all()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE password_reset_tokens, refresh_tokens, users "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
async def mongo() -> AsyncGenerator[AsyncIOMotorDatabase]:
    """A Mongo handle for seeding and asserting, on *this test's* event loop.

    Deliberately a separate client from the one the app uses, for a reason that
    is easy to get wrong. A motor client binds to the event loop it was created
    on, and `TestClient` runs the app in its own thread with its own loop — so a
    test that seeded through the app's cached client and then awaited it directly
    would be using one loop's client from another, which fails with an error that
    looks like a database problem and is not.

    Two clients against the same real database sidesteps it entirely: this one is
    a test tool, the app's is the app's, and neither ever sees the other's loop.
    Same shape as the `engine` fixture, and the same reason.
    """
    client = AsyncIOMotorClient(get_settings().mongodb_url, uuidRepresentation="standard")
    yield client[TEST_MONGO_DB]
    client.close()


@pytest.fixture(autouse=True)
async def _clean_mongo(mongo) -> AsyncGenerator[None]:
    """Empty the Mongo collections between tests, and drop the app's client.

    Closing the app's client is the Mongo equivalent of `NullPool`: it forces the
    next test to build a fresh one on its own loop rather than inheriting a
    client bound to a loop that has since closed.
    """
    yield
    for name in (FOOD_ITEMS, MEALS):
        await mongo[name].delete_many({})
    await close_client()


@pytest.fixture
async def catalogue(mongo) -> list[dict]:
    """Two seeded catalogue foods, covering both interesting unit kinds.

    Numbers are USDA's, recorded from a real response — an egg is 143 kcal per
    100 g and milk is 61. Written out rather than fetched so the suite neither
    needs the network nor spends the shared USDA budget, and so a test that
    depends on an exact total cannot start failing because upstream revised a
    value.
    """
    docs = [
        CatalogueFood(
            slug="egg",
            name_en="Egg",
            name_fr="Œuf",
            category="Protein",
            emoji="🥚",
            unit=UnitKind.COUNT,
            grams_per_unit=50,
            kcal=143,
            protein_g=12.6,
            carbs_g=0.72,
            fat_g=9.51,
            fibre_g=0,
            source_id="748967",
            portions=[
                Portion(label_en="1 egg", label_fr="1 œuf", amount=1, grams=50),
                Portion(
                    label_en="2 eggs", label_fr="2 œufs", amount=2, grams=100, is_default=True
                ),
            ],
            order=0,
        ),
        CatalogueFood(
            slug="milk",
            name_en="Milk",
            name_fr="Lait",
            category="Dairy",
            emoji="🥛",
            unit=UnitKind.MILLILITRES,
            # Milk is denser than water. This is the number the whole unit model
            # exists to keep honest.
            grams_per_unit=1.03,
            kcal=61,
            protein_g=3.15,
            carbs_g=4.8,
            fat_g=3.25,
            # Deliberately absent, so tests can prove a gap stays a gap rather
            # than becoming a confident zero on the way through a sum.
            fibre_g=None,
            source_id="746782",
            portions=[
                Portion(
                    label_en="1 glass",
                    label_fr="1 verre",
                    amount=250,
                    grams=257.5,
                    is_default=True,
                ),
            ],
            order=1,
        ),
    ]
    payload = [doc.model_dump(mode="json") for doc in docs]
    await mongo[FOOD_ITEMS].insert_many(payload)
    return payload


@pytest.fixture
def rate_limited() -> Iterator[None]:
    """Turn rate limiting on for a single test.

    Counters are cleared on the way in as well as out, so a test starts from a
    clean budget regardless of what ran before it.
    """
    os.environ["RATE_LIMIT_ENABLED"] = "true"
    get_settings.cache_clear()
    reset_all()
    yield
    os.environ["RATE_LIMIT_ENABLED"] = "false"
    get_settings.cache_clear()
    reset_all()


@pytest.fixture
async def session(engine) -> AsyncGenerator[AsyncSession]:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        yield s


@pytest.fixture
def client(engine) -> Iterator[TestClient]:
    """A TestClient whose requests hit the test database.

    The dependency override is the whole trick: FastAPI resolves `get_session`
    through this map, so the app under test uses our engine without any of its
    own code knowing it is being tested.
    """
    from app.db.session import get_session
    from app.main import app

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async def override_get_session() -> AsyncGenerator[AsyncSession]:
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
