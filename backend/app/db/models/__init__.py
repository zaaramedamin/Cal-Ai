"""ORM models.

Importing every model here matters more than it looks. Defining a model class is
what registers its table on `Base.metadata`, and Alembic's autogenerate compares
that metadata against the live database. A model that is never imported is
invisible to it — and autogenerate will cheerfully write a migration that DROPs
the table, because as far as it can tell the table should not exist.

`alembic/env.py` imports this package for exactly that reason.
"""

from app.db.models.user import RefreshToken, User

__all__ = ["RefreshToken", "User"]
