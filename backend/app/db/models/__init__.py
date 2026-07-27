"""ORM models.

Importing every model here matters more than it looks. Defining a model class is
what registers its table on `Base.metadata`, and Alembic's autogenerate compares
that metadata against the live database. A model that is never imported is
invisible to it — and autogenerate will cheerfully write a migration that DROPs
the table, because as far as it can tell the table should not exist.

`alembic/env.py` imports this package for exactly that reason.
"""

from app.db.models.diary import DiaryEntry, MealSlot
from app.db.models.food import Food, FoodPortion, FoodSource
from app.db.models.profile import UserProfile, WeightEntry
from app.db.models.user import PasswordResetToken, RefreshToken, RevocationReason, User

__all__ = [
    "DiaryEntry",
    "Food",
    "FoodPortion",
    "FoodSource",
    "MealSlot",
    "PasswordResetToken",
    "RefreshToken",
    "RevocationReason",
    "User",
    "UserProfile",
    "WeightEntry",
]
