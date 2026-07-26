"""Declarative base for every ORM model.

Phase 0 defines no tables — Phase 1 owns `users`. This exists now because
Alembic needs something to compare the live database against, and because the
naming convention below has to be in place *before* the first table is created.
Retrofitting it later means every existing constraint keeps its old random name.

Why the naming convention matters: left to itself, Postgres invents names like
`ck_users_1a2b3c`. When a later migration needs to drop or alter that constraint,
Alembic has to guess the name and usually gets it wrong, producing a migration
that works on your machine and fails on the deployed database. Deterministic
names make every constraint addressable from any migration.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
