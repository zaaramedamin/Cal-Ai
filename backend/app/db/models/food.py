"""Foods and their friendly portions.

Every row here is traceable. `source` and `source_id` are not decoration — they
are what lets any number in the app be followed back to USDA or Open Food Facts.
A food we cannot attribute is a food we should not be storing.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampedCreation, UUIDPrimaryKey


class FoodSource(enum.StrEnum):
    USDA = "usda"
    OFF = "off"

    #: The Tunisian national food composition table (INNTA).
    #:
    #: The reason this app exists. USDA measures American food and Ciqual
    #: measures French food; neither knows what pain tabouna, mlawi, rayeb,
    #: leben or a figue de barbarie contains. These rows do, and they carry a
    #: page number in the printed table so any one of them can be checked.
    #:
    #: They are also the least reliable mechanically — the table was digitised
    #: by OCR — which is why the importer cross-checks every row's macros
    #: against its stated energy and files the failures for a human to verify.
    INNTA = "innta"

    #: Ciqual, the French national table (ANSES).
    #:
    #: Clean, large, and full of composed dishes — which is what makes it
    #: useful here despite being French rather than Maghrebi: a great many
    #: everyday products are the same on both sides of the Mediterranean.
    CIQUAL = "ciqual"

    #: Created by a user. Still never invented by us — the user asserts it.
    USER = "user"
    #: The one source whose numbers are not measured.
    #:
    #: Written only when a photo scan identifies a food that neither USDA nor the
    #: cache can match, and only ever surfaced with a visible warning. It is
    #: excluded from ordinary food search, so a row like this can never reach a
    #: user who did not watch it being estimated. Everything else in this table
    #: is traceable to a measurement; this is traceable to a guess, and the app
    #: has to keep saying so.
    AI_ESTIMATE = "ai_estimate"


class ReviewStatus(enum.StrEnum):
    """Where a user-submitted food sits in the review pipeline.

    This governs *visibility*, not existence. A food is usable by its author the
    moment it is created — waiting for approval to log your own lunch would be
    absurd — and approval is what makes it visible to everybody else.
    """

    #: Author only. The default, and where a food stays unless it is submitted.
    PRIVATE = "private"
    #: Submitted and waiting. Still author-only.
    PENDING = "pending"
    #: Public. In everybody's search.
    APPROVED = "approved"
    #: Author only, permanently, with a reason they can read.
    REJECTED = "rejected"


class LlmVerdict(enum.StrEnum):
    """The model's opinion on a submission.

    Advice, never a decision. Kept in its own column beside `review_status` so it
    is always possible to tell whether a human actually looked — and so a future
    change cannot quietly promote the advice into an auto-approval.
    """

    PLAUSIBLE = "plausible"
    SUSPECT = "suspect"
    NOT_FOOD = "not_food"


class ReportReason(enum.StrEnum):
    """Why a user says a food is wrong.

    A closed list rather than free text alone, because the reason decides what
    can be *done* about it. "The numbers are wrong" on a USDA row is a different
    job from "this is a duplicate" — the first cannot be fixed by editing (the
    numbers are USDA's, and rewriting them would break the traceability the whole
    app rests on), the second is a merge.

    The note beside it is where the detail goes. Both together, because a reason
    with no detail is unactionable and free text alone cannot be counted.
    """

    #: Calories or macros do not match the label or the source.
    WRONG_NUMBERS = "wrong_numbers"
    #: Right food, wrong name or brand.
    WRONG_NAME = "wrong_name"
    #: Not a food at all, or offensive.
    NOT_FOOD = "not_food"
    #: Already in the database under another entry.
    DUPLICATE = "duplicate"
    OTHER = "other"

    #: Filed by the importer, not by a person. `reporter_id` is null on these.
    #:
    #: A food whose macros disagree with its own stated energy is either a
    #: transcription error or a genuinely unusual food, and the two are
    #: indistinguishable from here — so the importer says "check this" rather
    #: than guessing. It never edits or drops the row: the same rule as the
    #: model's screening verdict on submissions, which advises and never
    #: decides.
    IMPORT_CHECK = "import_check"


class ReportStatus(enum.StrEnum):
    OPEN = "open"
    #: The report was right, and something was done — see `resolution`.
    ACCEPTED = "accepted"
    #: Checked and the food is fine as it stands.
    DISMISSED = "dismissed"


class ReportResolution(enum.StrEnum):
    """What was actually done about an accepted report.

    Recorded rather than inferred, because "accepted" alone does not say whether
    a number changed — and for a food whose numbers came from USDA, the honest
    answer is usually that none did.
    """

    #: An admin edited the values. Only legitimate for a food a user wrote: the
    #: numbers on a USDA or Open Food Facts row are not ours to rewrite.
    CORRECTED = "corrected"
    #: Pulled out of search and the catalogue, left readable in existing diaries.
    #: The answer when a food is wrong at a source we do not control.
    WITHDRAWN = "withdrawn"


class FoodKind(enum.StrEnum):
    """What a food is to the app — a different question from where its numbers came from.

    `source` says USDA. `kind` says whether this row is a hand-picked item on the
    browse screen or a raw search result nobody curated. One FDC id can legitimately
    be either, and only the first should appear in the catalogue.

    This is what lets the catalogue live in `foods` instead of a table of its own.
    Keeping them apart is what forced `catalogue.materialise()` to exist — copying a
    Mongo document into a Postgres row so the diary had a foreign key target.
    """

    #: On the browse screen: curated name in both languages, a unit, portions.
    CATALOGUE = "catalogue"
    #: The USDA search cache. Raw upstream names, no curation.
    REFERENCE = "reference"
    #: Written by a user.
    CUSTOM = "custom"
    #: The one kind whose numbers are a guess. Excluded from ordinary search.
    ESTIMATE = "estimate"


class UnitKind(enum.StrEnum):
    """How a food is measured when a person talks about it."""

    GRAMS = "g"
    MILLILITRES = "ml"
    #: Whole items. The user picks a number and `grams_per_unit` converts it —
    #: "2 eggs" is how people think, "100 g of egg" is how nobody does.
    COUNT = "unit"


class Food(UUIDPrimaryKey, TimestampedCreation, Base):
    """A food, normalised to per 100 g (or per 100 ml for liquids).

    **Why nullable nutrients matter more than they look.**

    `kcal`, `protein_g`, `carbs_g` and `fat_g` are NOT NULL: a food without them
    is useless for tracking and we reject it at import rather than store a hole.

    `sugars_g`, `saturated_fat_g`, `fibre_g` and `sodium_mg` are nullable,
    because USDA Foundation entries genuinely omit them. This is the schema-level
    enforcement of "never invent a nutrition value": if the source does not
    report fibre, the column is NULL and the app renders an em dash, not `0 g`.

    Defaulting those to zero would be inventing data — and worse, it would be
    invisible. A user would see a confident `0 g fibre` for wholemeal bread and
    have no way to know the number was fabricated by our import script.
    """

    __tablename__ = "foods"

    # One row per upstream item. The unique constraint is what makes the cache a
    # cache rather than a pile of duplicates: re-importing updates in place.
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_food_source_id"),
        # Slugs name catalogue foods and appear in photo filenames, so a
        # duplicate would make "the photo for chicken-breast" ambiguous.
        UniqueConstraint("slug", name="uq_food_slug"),
        # The review queue is read as "pending, oldest first" on every admin load.
        Index("ix_foods_review_queue", "review_status", "submitted_at"),
        # How the browse screen reads: grouped by category, deliberately ordered
        # within each. Without it, every catalogue load is a sequential scan.
        Index("ix_foods_catalogue", "kind", "category", "sort_order"),
    )

    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)

    #: See `FoodKind`. Defaults to `reference` so an ordinary cached search result
    #: needs to say nothing, and only a curated row declares itself.
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FoodKind.REFERENCE, server_default="reference"
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    # --- catalogue only, null for everything else -------------------------
    #: Stable hand-written key ("chicken-breast"). What the seeder is idempotent
    #: on and what photo filenames are matched against.
    slug: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)

    #: A food name is not a UI string. "Blanc de poulet" is not something a
    #: dictionary produces from "Chicken breast", and getting it wrong in a
    #: nutrition app is worse than in most places — so it is written, not
    #: translated. Null wherever nobody has written one.
    name_fr: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    category: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    emoji: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)

    #: Position within a category, so the list reads deliberately rather than
    #: alphabetically.
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    #: Filename in `food_photos`, or null while none has been shot — the app
    #: renders the emoji in the meantime.
    photo: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)

    #: Drives whether portions read as grams or millilitres. Both are stored as
    #: grams internally; this only changes the label.
    is_liquid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: How this food is counted. See `UnitKind`.
    unit: Mapped[str] = mapped_column(
        String(8), nullable=False, default=UnitKind.GRAMS, server_default="g"
    )

    #: What **one** of this food's units weighs, in grams.
    #:
    #: Three decimals because it doubles as a density for liquids — milk is
    #: 1.03 g/ml, oil 0.91 — and rounding those to two puts a visible error on a
    #: litre. Present for every food, not only countables: the portion list only
    #: covers the sizes we thought to offer, so a user typing 300 ml when no
    #: 300 ml portion exists still needs a conversion, and the tempting fallback
    #: — assuming water — is a 3% error on milk and 9% on oil. One number per
    #: food, used by every conversion, means there is nowhere for that
    #: assumption to hide.
    grams_per_unit: Mapped[float] = mapped_column(
        Numeric(8, 3), nullable=False, default=1, server_default="1"
    )

    # --- per 100 g / 100 ml, always -------------------------------------
    # Numeric rather than float throughout. These are the numbers the whole app
    # exists to report, and binary floating point cannot represent 0.1 exactly.
    kcal: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    protein_g: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    carbs_g: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    fat_g: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)

    sugars_g: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True, default=None)
    saturated_fat_g: Mapped[float | None] = mapped_column(
        Numeric(7, 2), nullable=True, default=None
    )
    fibre_g: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True, default=None)
    sodium_mg: Mapped[float | None] = mapped_column(Numeric(9, 2), nullable=True, default=None)

    #: When we last pulled this from upstream. Phase 6 uses it to refresh stale
    #: rows; for now it makes "how old is this number" answerable.
    data_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    #: Who created it, for user-authored foods. Null for USDA and Open Food Facts.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )

    # --- review, for user-submitted foods ---------------------------------
    #: See `ReviewStatus`. Irrelevant for USDA and Open Food Facts rows, which
    #: have no owner and are visible to everybody regardless.
    review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReviewStatus.PRIVATE, server_default="private"
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    #: SET NULL rather than CASCADE — an admin leaving must not delete the foods
    #: they approved. The decision outlives the account that made it.
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    #: Shown to the author, so a refusal is explainable rather than silent.
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)

    #: The model's advice and its reasoning — never the decision. See `LlmVerdict`.
    llm_verdict: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    llm_reason: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)

    # --- withdrawal, for foods reported as wrong --------------------------
    #: Set when a report is upheld and the numbers cannot be fixed here.
    #:
    #: **Why withdrawal rather than deletion.** A wrong food is usually already
    #: in somebody's diary. Deleting the row would either cascade their history
    #: away or fail on the foreign key, and both are worse than the wrong number:
    #: a past entry is a record of what they logged, not a claim we are still
    #: making. Withdrawal takes the food out of search and the catalogue and
    #: leaves every existing reference readable.
    #:
    #: **Why it is separate from `review_status`.** That column governs
    #: *submissions*, and `is_public` treats a null owner as public outright — so
    #: rejecting an Open Food Facts row would have changed nothing at all. Most
    #: reports are against exactly those rows.
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    #: Why, in words. Shown wherever a withdrawn food still appears — a diary
    #: entry pointing at one should say what happened rather than look normal.
    withdrawn_reason: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)

    @property
    def is_public(self) -> bool:
        """Visible to users other than the author."""
        if self.withdrawn_at is not None:
            return False
        return self.owner_id is None or self.review_status == ReviewStatus.APPROVED

    @property
    def is_correctable(self) -> bool:
        """Whether an admin may edit these numbers in place.

        The question is not "who owns this row" but **is there an upstream that
        will contradict us**.

        *No, for USDA and Open Food Facts.* Those ids resolve to a live record
        we re-fetch, so an edit here is overwritten on the next refresh and,
        until then, leaves a row claiming a provenance its figures no longer
        have. A wrong one gets withdrawn and reported upstream.

        *Yes, for INNTA and Ciqual.* Those are static tables imported once from
        a printed or published source and never re-fetched. When a reviewer
        opens page 31, reads the real figure and types it in, that is
        *restoring* what the table says — the OCR was the error, not the table.
        Forbidding it would mean the only remedy for a mistyped Tunisian food is
        deleting it from an app whose entire point is having those foods.

        *Yes, for a user's own food*, which was always theirs to fix.
        """
        return self.source not in (FoodSource.USDA, FoodSource.OFF)

    portions: Mapped[list["FoodPortion"]] = relationship(
        back_populates="food", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Food {self.name!r} ({self.source}:{self.source_id})>"


class FoodPortion(UUIDPrimaryKey, TimestampedCreation, Base):
    """A friendly unit mapped to a gram weight.

    Portions are a separate table rather than columns on `foods` because a food
    has many of them — "1 medium banana", "1 cup sliced", "1 small" — and the set
    differs per food. Storing them inline would mean a fixed number of slots and
    a schema change to add one.

    Everything is grams underneath. The label is presentation; the gram weight is
    the fact. That is what keeps a diary entry comparable across foods logged in
    completely different units.
    """

    __tablename__ = "food_portions"

    food_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("foods.id", ondelete="CASCADE"), nullable=False, index=True
    )

    label: Mapped[str] = mapped_column(String(96), nullable=False)
    #: The French label. Null for cached USDA portions, which have no curated
    #: translation and must not be given an invented one.
    label_fr: Mapped[str | None] = mapped_column(String(96), nullable=True, default=None)

    grams: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)

    #: How many of the food's own unit this portion is — the "2" in "2 eggs".
    #: What the user picks; `grams` is what the diary stores underneath. Null on
    #: cached USDA portions, which are gram weights with no unit behind them.
    amount: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True, default=None)

    #: The portion offered first. Falls back to 100 g when nothing is marked.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    food: Mapped[Food] = relationship(back_populates="portions")

    def __repr__(self) -> str:
        return f"<FoodPortion {self.label!r} = {self.grams}g>"


class FoodPhoto(TimestampedCreation, Base):
    """A catalogue thumbnail, stored as bytes.

    In the database rather than on disk, for the reason it was in Mongo: a folder
    is server-local state that has to be backed up separately, survive a redeploy
    and be shared between instances. At ~20 KB each the whole set is under a
    megabyte, which is not a size worth building a storage service around.

    The primary key is the **filename**, which embeds a hash of the bytes, and
    that is what makes the serving URL immutable: a replaced photo gets a
    different name, so a client can cache one forever and still see a new one the
    moment it is published. Cache invalidation by renaming rather than by header.
    """

    __tablename__ = "food_photos"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)

    food_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("foods.id", ondelete="CASCADE"), nullable=False, index=True
    )

    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    # Where the photograph came from and who is owed credit for it. Nullable
    # because a photograph taken for this project owes credit to nobody, and a
    # column that forces "Unknown" onto those rows says something untrue.
    #
    # These live beside the bytes rather than in an import log because the credit
    # has to be renderable wherever the image is. A CC BY-SA licence is a
    # condition attached to the file, so it travels with the file.
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    license: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attribution: Mapped[str | None] = mapped_column(String(256), nullable=True)

    def __repr__(self) -> str:
        return f"<FoodPhoto {self.name!r} ({self.width}×{self.height})>"


class FoodReport(UUIDPrimaryKey, TimestampedCreation, Base):
    """Somebody saying a food's numbers are wrong.

    The other direction of travel from `review`. That pipeline decides what gets
    *in*; this one is how anything already in — including USDA and Open Food
    Facts rows nobody here typed — gets challenged.

    It matters because of what the app promises. "Every number traceable to its
    source" is only worth something if a source being wrong is reportable:
    Open Food Facts is volunteer-entered from labels, USDA entries can be decades
    old, and an approved user submission was checked by one person once. Without
    this table the only honest thing to say is "the numbers come from somewhere
    else, so they are somebody else's problem", which is not what the app claims.

    A report is never itself a change. It opens a question a person answers —
    the same rule as `llm_verdict` in review: advice on the record, decision on a
    human. Nothing here can alter a nutrition value on its own.
    """

    __tablename__ = "food_reports"

    __table_args__ = (
        # One open report per person per food. Without it, tapping the button
        # twice files two, and a food with ten duplicates from one account looks
        # like ten people disagreeing.
        #
        # Partial, on `status`, so the same person can report the same food again
        # later — a fix that did not work is a legitimate second report, and a
        # blanket unique constraint would silence it forever.
        Index(
            "uq_food_report_open",
            "food_id",
            "reporter_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        # How the admin queue reads: open reports, oldest first.
        Index("ix_food_reports_queue", "status", "created_at"),
    )

    food_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("foods.id", ondelete="CASCADE"), nullable=False
    )

    #: SET NULL, not CASCADE. A report is evidence about a food, and it stays
    #: true after the person who filed it deletes their account. The same
    #: reasoning as `reviewed_by` on `Food`.
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    #: See `ReportReason`.
    reason: Mapped[str] = mapped_column(String(16), nullable=False)

    #: What the label actually says, usually. Optional, because forcing a
    #: paragraph out of somebody is how a report button goes unused — but the
    #: schema keeps it because "kcal reads 250, we say 180" is the whole report.
    note: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ReportStatus.OPEN, server_default="open"
    )

    #: What was done. Null while open, and null on a dismissal — nothing was.
    resolution: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)

    #: Shown to the reporter. A report answered with silence teaches people not
    #: to bother, and the whole value here is that somebody bothers.
    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    food: Mapped[Food] = relationship()

    def __repr__(self) -> str:
        return f"<FoodReport {self.reason} on {self.food_id} ({self.status})>"
