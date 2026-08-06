"""food submission review

Revision ID: d1e5b73a9c48
Revises: c9d3f4a81b52
Create Date: 2026-08-01 11:00:00.000000

A review pipeline for user-submitted foods, so the database can grow from real
users without a stranger's mistake reaching everyone.

**Review state lives on `foods`, not in a separate submissions table.** The food
row has to exist the moment it is created, because its author logs it into their
diary immediately — waiting for approval to record your own lunch would be
absurd. Approval therefore changes a food's *visibility*, not its existence,
which is one column rather than a second table and a promotion step that could
half-fail.

The states:

  private    Author only. The default, and where a food stays unless the author
             asks for it to be shared.
  pending    Submitted. Still author-only, now waiting on review.
  approved   Public. Visible in everybody's search.
  rejected   Author only, permanently, with a reason they can read.

Rejection does not delete. The author's diary references the food, and while the
nutrient snapshot means an entry survives its food vanishing, leaving someone's
history intact and readable is better than technically-not-broken.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e5b73a9c48"
down_revision: str | Sequence[str] | None = "c9d3f4a81b52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "foods",
        sa.Column("review_status", sa.String(16), nullable=False, server_default="private"),
    )
    op.create_check_constraint(
        "review_status",
        "foods",
        "review_status IN ('private', 'pending', 'approved', 'rejected')",
    )

    op.add_column("foods", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("foods", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "foods",
        sa.Column(
            "reviewed_by",
            sa.UUID(as_uuid=True),
            # SET NULL, not CASCADE: an admin leaving must not delete the foods
            # they approved. The decision outlives the account that made it.
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    #: Shown to the author when their submission is rejected or edited, so a
    #: refusal is explainable rather than silent.
    op.add_column("foods", sa.Column("review_note", sa.String(500), nullable=True))

    # --- the LLM's opinion, kept separate from the decision -----------------
    #
    # Two columns rather than one status, because the model's verdict is advice
    # and the admin's is the decision. Collapsing them would make it impossible
    # to tell afterwards whether a human ever looked — and would let a future
    # change quietly promote the advice into an auto-approval.
    op.add_column("foods", sa.Column("llm_verdict", sa.String(16), nullable=True))
    op.create_check_constraint(
        "llm_verdict",
        "foods",
        "llm_verdict IS NULL OR llm_verdict IN ('plausible', 'suspect', 'not_food')",
    )
    op.add_column("foods", sa.Column("llm_reason", sa.String(500), nullable=True))

    # The review queue is read as "pending, oldest first" on every admin load.
    op.create_index(
        "ix_foods_review_queue",
        "foods",
        ["review_status", "submitted_at"],
    )

    # --- who may review ------------------------------------------------------
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
    op.drop_index("ix_foods_review_queue", table_name="foods")
    op.drop_constraint("llm_verdict", "foods", type_="check")
    op.drop_column("foods", "llm_reason")
    op.drop_column("foods", "llm_verdict")
    op.drop_column("foods", "review_note")
    op.drop_column("foods", "reviewed_by")
    op.drop_column("foods", "reviewed_at")
    op.drop_column("foods", "submitted_at")
    op.drop_constraint("review_status", "foods", type_="check")
    op.drop_column("foods", "review_status")
