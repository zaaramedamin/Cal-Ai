"""allow users without a local password

Revision ID: b4e2a91c7f36
Revises: a7f3c81b2d94
Create Date: 2026-07-30 12:00:00.000000

Supabase Auth owns credentials from here on, so an account authenticated that way
has no password of ours to hash. `password_hash` therefore becomes nullable, and
the null means something precise: **this account is authenticated by Supabase**.

That is deliberately not a separate boolean. A `provider` column beside a
nullable hash would make "supabase account that also has a local password" and
"local account with no password" representable, and both are states nothing
should ever be in. One nullable column can only express the two cases that are
real.

Nothing is backfilled and nothing is dropped. Existing accounts keep their hashes
and keep working, because the two auth paths run side by side until the mobile
app has moved over.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4e2a91c7f36"
down_revision: str | Sequence[str] | None = "a7f3c81b2d94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    """Reverse, refusing rather than inventing.

    Making the column NOT NULL again cannot succeed while Supabase-authenticated
    rows exist, and there is no honest value to give them — a placeholder hash
    would be a password nobody knows that argon2 would still try to verify. The
    migration therefore fails loudly and names the rows in the way, which is the
    correct outcome: the fix is a decision about those accounts, not a default.
    """
    connection = op.get_bind()
    orphans = connection.execute(
        sa.text("SELECT count(*) FROM users WHERE password_hash IS NULL")
    ).scalar_one()

    if orphans:
        raise RuntimeError(
            f"{orphans} account(s) are authenticated by Supabase and have no local "
            f"password. Downgrading would require inventing one. Delete or migrate "
            f"those accounts first:\n"
            f"  SELECT id, email FROM users WHERE password_hash IS NULL;"
        )

    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
