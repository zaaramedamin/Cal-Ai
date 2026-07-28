"""MongoDB client and collections.

One client for the process, opened lazily and closed on shutdown. `AsyncIOMotorClient`
is itself a pool — constructing one per request would open and close sockets on
every call, which is the single most common way to make a Mongo-backed API slow.

**On the trade-off this database represents.** Postgres gave the diary a foreign
key to foods with `ON DELETE SET NULL`, so deleting a food could never orphan a
diary row or silently rewrite someone's history. Mongo has no such guarantee, so
that rule now lives in application code and in the nutrient snapshot: every diary
entry already stores the nutrients it was logged with, which is what makes a
missing food row survivable rather than corrupting. The snapshot was always the
real protection; the foreign key was the belt to its braces.
"""

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, TEXT, IndexModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    """The process-wide client, created on first use."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(
            settings.mongodb_url,
            # Fail fast rather than hanging. The default is 30 seconds, which on
            # a stopped container means the phone sits on a spinner for half a
            # minute before showing an error it could have shown immediately.
            serverSelectionTimeoutMS=5000,
            uuidRepresentation="standard",
        )
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[get_settings().mongodb_db]


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


# --------------------------------------------------------------------------- #
# Collections
# --------------------------------------------------------------------------- #

FOOD_ITEMS = "food_items"
MEALS = "meals"


def food_items() -> Any:
    return get_db()[FOOD_ITEMS]


def meals() -> Any:
    return get_db()[MEALS]


async def ensure_indexes() -> None:
    """Create indexes if they are missing.

    Mongo has no migrations, so index creation has to happen somewhere. Doing it
    at startup is idempotent — `create_indexes` is a no-op when an index already
    exists with the same definition — and it means a fresh clone gets a correct
    database from `docker compose up` without a separate setup step to forget.

    The cost is a few milliseconds on boot, paid once.
    """
    await food_items().create_indexes(
        [
            # The catalogue is browsed by category and searched by name. A text
            # index gives word-level matching, which is what the search screen
            # wants — `name: /oat/` would scan every document.
            IndexModel([("slug", ASCENDING)], unique=True, name="uq_slug"),
            IndexModel([("category", ASCENDING), ("order", ASCENDING)], name="ix_category"),
            IndexModel([("name.en", TEXT), ("name.fr", TEXT)], name="tx_names"),
        ]
    )
    await meals().create_indexes(
        [
            IndexModel([("user_id", ASCENDING), ("name", ASCENDING)], name="ix_user_meals"),
        ]
    )
    logger.info("MongoDB indexes ensured")
