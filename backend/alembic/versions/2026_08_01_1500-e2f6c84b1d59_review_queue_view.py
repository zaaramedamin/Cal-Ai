"""review queue view

Revision ID: e2f6c84b1d59
Revises: d1e5b73a9c48
Create Date: 2026-08-01 15:00:00.000000

A view so the review queue is workable from Supabase Studio without writing a
join every time.

**Why a view and not an admin app.** The reviewer is one person with a handful of
submissions a day. Studio already renders a table, sorts it and filters it; the
only thing missing was a shape worth looking at — the raw `foods` table is forty
columns wide and most of them are irrelevant to a decision.

Filtering happens in Studio's own UI: `verdict = 'not_food'` clears the spam pile
in one pass, `verdict = 'plausible'` leaves the ones deserving real attention.
That is the same filter the API exposes, in the place the work actually happens.

Deciding is still an UPDATE, and deliberately so. A view cannot approve anything
by accident.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e2f6c84b1d59"
down_revision: str | Sequence[str] | None = "d1e5b73a9c48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEW = """
CREATE OR REPLACE VIEW review_queue AS
SELECT
    f.id,
    f.submitted_at,
    -- The model's triage, first: it is what decides how much attention the row
    -- below it deserves.
    f.llm_verdict          AS verdict,
    f.llm_reason           AS verdict_reason,

    f.name,
    f.brand,
    f.kcal,
    f.protein_g,
    f.carbs_g,
    f.fat_g,

    -- What the macros imply, beside what was declared. A reviewer comparing two
    -- numbers spots a mistyped decimal point instantly, where reading one number
    -- tells them nothing. The importer already refuses anything outside 0.5-2x,
    -- so what survives to here is plausible arithmetic that may still be the
    -- wrong food.
    ROUND((4 * f.protein_g + 4 * f.carbs_g + 9 * f.fat_g)::numeric, 0)
                           AS kcal_implied_by_macros,

    f.sugars_g,
    f.saturated_fat_g,
    f.fibre_g,
    f.sodium_mg,

    u.email                AS submitted_by,
    -- How many foods this person has had accepted before. A contributor with a
    -- record earns a faster read; a first submission earns a careful one.
    (
        SELECT count(*)
        FROM foods prior
        WHERE prior.owner_id = f.owner_id
          AND prior.review_status = 'approved'
    )                      AS author_approved_count
FROM foods f
LEFT JOIN users u ON u.id = f.owner_id
WHERE f.review_status = 'pending'
ORDER BY f.submitted_at;
"""


def upgrade() -> None:
    op.execute(VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS review_queue")
