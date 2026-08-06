"""absorb catalogue, meals and photos from mongo

Revision ID: a7f3c81b2d94
Revises: e91d8f58323d
Create Date: 2026-07-29 10:30:00.000000

The end of the two-database split. Everything that lived in MongoDB — the
curated food catalogue, saved meals, and the catalogue photos — gets a home in
Postgres, where the constraints that make this data trustworthy can actually be
enforced.

**The catalogue joins `foods` rather than getting its own table.** A catalogue
food *is* a USDA food: it was seeded from a specific FDC id and `upsert_food` is
already keyed on `(source, source_id)`, so a curated "Egg" and a searched
"Egg, whole, raw" were always meant to be one row. Keeping them apart is what
forced `catalogue.materialise()` to exist — a function whose entire job was
copying a Mongo document into a Postgres row so the diary had something to point
its foreign key at. One table deletes that function and the class of bug it
carried.

The catalogue-only columns are therefore nullable additions to `foods`, guarded
by a CHECK so a row claiming to be catalogue cannot be missing the things a
catalogue row needs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7f3c81b2d94"
down_revision: str | Sequence[str] | None = "e91d8f58323d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- foods: the catalogue's columns -----------------------------------
    #
    # `kind` answers "what is this food to the app", which is a different
    # question from `source` ("where did its numbers come from"). A USDA row can
    # be a curated menu item or a raw search hit, and only the first should
    # appear on the browse screen.
    op.add_column(
        "foods",
        sa.Column("kind", sa.String(16), nullable=False, server_default="reference"),
    )
    op.add_column("foods", sa.Column("slug", sa.String(64), nullable=True))
    op.add_column("foods", sa.Column("name_fr", sa.String(255), nullable=True))
    op.add_column("foods", sa.Column("category", sa.String(64), nullable=True))
    op.add_column("foods", sa.Column("emoji", sa.String(16), nullable=True))
    op.add_column(
        "foods", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("foods", sa.Column("unit", sa.String(8), nullable=False, server_default="g"))
    # What one of this food's units weighs. Three decimal places because it
    # doubles as a density for liquids — milk is 1.03 g/ml, oil 0.91 — and
    # rounding those to two would put a visible error on a litre.
    op.add_column(
        "foods",
        sa.Column(
            "grams_per_unit",
            sa.Numeric(8, 3),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column("foods", sa.Column("photo", sa.String(128), nullable=True))

    # Existing rows predate `kind`, so classify them from what they already say.
    op.execute(
        """
        UPDATE foods SET kind = CASE
            WHEN source = 'ai_estimate' THEN 'estimate'
            WHEN source = 'user'        THEN 'custom'
            ELSE 'reference'
        END
        """
    )

    # Bare constraint names throughout: the metadata naming convention in
    # `db/base.py` prepends `ck_<table>_`, so passing the full name here would
    # produce `ck_foods_ck_foods_kind`.
    op.create_unique_constraint("uq_food_slug", "foods", ["slug"])
    op.create_check_constraint(
        "kind",
        "foods",
        "kind IN ('catalogue', 'reference', 'custom', 'estimate')",
    )
    op.create_check_constraint("unit", "foods", "unit IN ('g', 'ml', 'unit')")
    # A catalogue row without a slug could never be looked up by the browse
    # screen, and one without a category could never be grouped into a section.
    # Both are silent failures — the food simply does not appear — so the
    # database refuses them instead.
    op.create_check_constraint(
        "catalogue_complete",
        "foods",
        "kind <> 'catalogue' OR (slug IS NOT NULL AND category IS NOT NULL)",
    )
    op.create_check_constraint("grams_per_unit_positive", "foods", "grams_per_unit > 0")
    op.create_index("ix_foods_catalogue", "foods", ["kind", "category", "sort_order"])

    # ---- food_portions: bilingual labels and the amount ---------------------
    #
    # The old table had one unlabelled-language string. The catalogue needs both
    # languages, and `amount` — "2" in "2 eggs" — which is what the user actually
    # picks, with `grams` being what the diary stores underneath.
    op.add_column("food_portions", sa.Column("label_fr", sa.String(96), nullable=True))
    op.add_column("food_portions", sa.Column("amount", sa.Numeric(8, 2), nullable=True))
    op.create_check_constraint(
        "amount_positive", "food_portions", "amount IS NULL OR amount > 0"
    )

    # ---- food_photos --------------------------------------------------------
    #
    # In the database rather than on disk, for the same reason they were in Mongo:
    # a folder is server-local state that has to be backed up separately, survive
    # a redeploy and be shared between instances. At ~20 KB each this is under a
    # megabyte in total, which is not a size worth building a storage service for.
    op.create_table(
        "food_photos",
        # The filename, with a hash of the bytes in it. Keying on this rather
        # than on food_id is what makes the serving URL immutable: a replaced
        # photo gets a different name, so clients can cache one forever and still
        # see a new one immediately. Cache invalidation by renaming.
        sa.Column("name", sa.String(128), primary_key=True),
        sa.Column(
            "food_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("foods.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ---- meals and their items ---------------------------------------------
    #
    # A saved plate the user logs again in one tap. Kept separate from `recipes`:
    # a recipe divides a total into servings and is costed per portion, a meal is
    # a shortcut for a plate eaten as-is.
    op.create_table(
        "meals",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_meals_user_name", "meals", ["user_id", "name"])

    op.create_table(
        "meal_items",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "meal_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("meals.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # RESTRICT, matching recipe_ingredients. A meal holds no nutrient
        # snapshot — it is costed live from its items — so losing one would make
        # it silently under-report. Refusing the delete is the only answer that
        # cannot corrupt a total.
        sa.Column(
            "food_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("foods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # In the food's own unit: 2 eggs, 250 ml, 30 g.
        sa.Column("amount", sa.Numeric(8, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        # A food appears once per meal. Adding the same item twice is a mistake
        # the user cannot see in a list, so it is prevented rather than allowed
        # to silently double a total.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("meal_id", "food_id", name="uq_meal_item"),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
    )


def downgrade() -> None:
    """Reverse cleanly.

    Losing this migration means losing the catalogue, saved meals and photos
    from Postgres. That is recoverable rather than catastrophic — the catalogue
    reseeds from USDA with one command, and until the services are switched over
    the Mongo copies are still there untouched.
    """
    op.drop_table("meal_items")
    op.drop_index("ix_meals_user_name", table_name="meals")
    op.drop_table("meals")
    op.drop_table("food_photos")

    # Bare names here too. `drop_constraint` runs the name through the same
    # naming convention as `create_check_constraint`, so passing the full
    # `ck_foods_kind` would expand to `ck_foods_ck_foods_kind` and fail on a
    # constraint that does not exist.
    op.drop_constraint("amount_positive", "food_portions", type_="check")
    op.drop_column("food_portions", "amount")
    op.drop_column("food_portions", "label_fr")

    op.drop_index("ix_foods_catalogue", table_name="foods")
    op.drop_constraint("grams_per_unit_positive", "foods", type_="check")
    op.drop_constraint("catalogue_complete", "foods", type_="check")
    op.drop_constraint("unit", "foods", type_="check")
    op.drop_constraint("kind", "foods", type_="check")
    op.drop_constraint("uq_food_slug", "foods", type_="unique")
    for column in (
        "photo",
        "grams_per_unit",
        "unit",
        "sort_order",
        "emoji",
        "category",
        "name_fr",
        "slug",
        "kind",
    ):
        op.drop_column("foods", column)
