"""add water tracking

Revision ID: c9d3f4a81b52
Revises: b4e2a91c7f36
Create Date: 2026-07-31 14:00:00.000000

One row per drink rather than a running total per day. Totals are what the screen
shows, but they are not what the user does: they tap "+250 ml" and sometimes tap
it by mistake. A stored total can only be corrected by arithmetic; a list of
entries can have its last item removed, which is what "undo" means to everyone
who is not a programmer.

**The goal lives on the profile and is nullable.** A default would have to be
invented, and this project does not invent numbers a user might read as advice.
Null means "no goal set", the screen shows the intake without a target, and the
number only appears once someone has chosen one.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d3f4a81b52"
down_revision: str | Sequence[str] | None = "b4e2a91c7f36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "water_entries",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The user's local calendar day, set server-side from their timezone —
        # the same rule as diary entries. A drink at 11pm belongs to that day
        # regardless of what UTC thinks.
        sa.Column("local_date", sa.Date(), nullable=False),
        # Millilitres as an integer. Water needs no decimal place: nobody drinks
        # 250.5 ml, and an integer cannot accumulate rounding error across a day
        # of additions the way a float can.
        sa.Column("millilitres", sa.Integer(), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("millilitres > 0", name="millilitres_positive"),
        # A glass is not five litres. Bounded because water intoxication is real
        # and a typo'd 25000 would otherwise render as a plausible-looking day.
        sa.CheckConstraint("millilitres <= 5000", name="millilitres_bounded"),
    )
    # Every read is "this user, this day", exactly like the diary.
    op.create_index("ix_water_entries_user_date", "water_entries", ["user_id", "local_date"])

    op.add_column(
        "user_profiles",
        sa.Column("water_goal_ml", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "water_goal_sane",
        "user_profiles",
        "water_goal_ml IS NULL OR (water_goal_ml >= 500 AND water_goal_ml <= 10000)",
    )


def downgrade() -> None:
    op.drop_constraint("water_goal_sane", "user_profiles", type_="check")
    op.drop_column("user_profiles", "water_goal_ml")
    op.drop_index("ix_water_entries_user_date", table_name="water_entries")
    op.drop_table("water_entries")
