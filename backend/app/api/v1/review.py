"""Food submission, review, and reports against foods already in.

Two pipelines, opposite directions, one module — because they share the admin
gate and the rule that a person makes every decision:

    author  submits  ->  model screens  ->  admin decides  ->  everybody sees it
    anyone  reports  ->  admin checks   ->  corrected, withdrawn, or dismissed

The author keeps using their food throughout submission. Approval changes who
*else* can see it, never whether it works.

The second pipeline is the one that keeps "every number traceable to its source"
from being an empty claim. Open Food Facts is volunteer-entered from labels,
USDA rows can be decades old, and an approved submission was read by one person
once. Reporting is how a wrong number gets challenged after it is already in.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser
from app.db.models.food import (
    Food,
    FoodPortion,
    FoodReport,
    ReportReason,
    ReportResolution,
    ReportStatus,
    ReviewStatus,
)
from app.db.models.user import User
from app.db.session import get_session
from app.schemas.food import FoodRead
from app.services.food_review import FoodReviewer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review", tags=["review"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_reviewer() -> FoodReviewer:
    """Overridable in tests, so no test calls Gemini for real."""
    return FoodReviewer()


ReviewerDep = Annotated[FoodReviewer, Depends(get_reviewer)]


async def require_admin(user: CurrentUser) -> User:
    """Gate every admin route.

    A dependency rather than a check inside each handler: a route is protected
    because its signature says so, which is visible in the code and impossible to
    forget by editing something else. The same reasoning as `get_current_user`.

    404 rather than 403 for a non-admin. A 403 confirms the endpoint exists and
    that the caller is simply not allowed, which maps the admin surface for
    anyone probing; a 404 says nothing.
    """
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


class SubmissionRead(BaseModel):
    """A submission as the author or an admin sees it."""

    model_config = ConfigDict(from_attributes=True)

    food: FoodRead
    review_status: str
    submitted_at: datetime | None
    reviewed_at: datetime | None
    review_note: str | None
    #: The model's opinion. Advice for the reviewer, and shown to the author only
    #: after a decision — a "suspect" verdict on its own is not a refusal.
    llm_verdict: str | None
    llm_reason: str | None


def _to_read(food: Food) -> SubmissionRead:
    return SubmissionRead(
        food=FoodRead.model_validate(food),
        review_status=food.review_status,
        submitted_at=food.submitted_at,
        reviewed_at=food.reviewed_at,
        review_note=food.review_note,
        llm_verdict=food.llm_verdict,
        llm_reason=food.llm_reason,
    )


async def _load(session: AsyncSession, food_id: uuid.UUID) -> Food | None:
    return (
        await session.execute(
            select(Food).where(Food.id == food_id).options(selectinload(Food.portions))
        )
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Author
# --------------------------------------------------------------------------- #


@router.post(
    "/foods/{food_id}/submit",
    response_model=SubmissionRead,
    summary="Offer one of your foods to the shared database",
)
async def submit_food(
    food_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    reviewer: ReviewerDep,
) -> SubmissionRead:
    """Put a food into the review queue, screening it on the way in.

    Screening happens here rather than in a background job because the queue is
    the thing being protected: a submission that arrives already sorted is one a
    reviewer can triage at a glance. If the screening fails the food is still
    submitted — an outage at Google must not be able to block contributions.
    """
    food = await _load(session, food_id)
    if food is None or food.owner_id != user.id:
        # Same 404 for "no such food" and "not yours". Distinguishing them would
        # let anyone confirm a food id exists by submitting it.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such food.")

    if food.review_status in (ReviewStatus.PENDING, ReviewStatus.APPROVED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "That food is already in the queue."
                if food.review_status == ReviewStatus.PENDING
                else "That food is already shared."
            ),
        )

    opinion = await reviewer.assess(food)
    if opinion is not None:
        food.llm_verdict = opinion.verdict.value
        food.llm_reason = opinion.reason

    food.review_status = ReviewStatus.PENDING
    food.submitted_at = datetime.now(UTC)
    # Cleared, so a resubmission after a rejection is not read against the old
    # decision.
    food.review_note = None
    food.reviewed_at = None
    food.reviewed_by = None

    await session.commit()
    logger.info(
        "Food %s submitted by %s (screening: %s)",
        food.id,
        user.id,
        food.llm_verdict or "unavailable",
    )

    return _to_read(await _load(session, food.id))  # type: ignore[arg-type]


@router.get(
    "/foods/mine",
    response_model=list[SubmissionRead],
    summary="Your submissions and where they stand",
)
async def my_submissions(user: CurrentUser, session: SessionDep) -> list[SubmissionRead]:
    rows = (
        (
            await session.execute(
                select(Food)
                .where(Food.owner_id == user.id, Food.review_status != ReviewStatus.PRIVATE)
                .options(selectinload(Food.portions))
                .order_by(Food.submitted_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_to_read(food) for food in rows]


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #


@router.get(
    "/queue",
    response_model=list[SubmissionRead],
    summary="Submissions waiting for a decision",
)
async def review_queue(
    admin: AdminUser,
    session: SessionDep,
    verdict: Annotated[
        Literal["plausible", "suspect", "not_food"] | None,
        Query(description="Filter by the model's screening verdict"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[SubmissionRead]:
    """Oldest first, so nothing waits indefinitely behind newer arrivals.

    The verdict filter is the point of screening: a reviewer can take the
    `not_food` pile in one pass and give the `plausible` ones the attention they
    deserve, instead of reading everything at the same depth.
    """
    query = (
        select(Food)
        .where(Food.review_status == ReviewStatus.PENDING)
        .options(selectinload(Food.portions))
        .order_by(Food.submitted_at)
        .limit(limit)
    )
    if verdict is not None:
        query = query.where(Food.llm_verdict == verdict)

    rows = (await session.execute(query)).scalars().all()
    return [_to_read(food) for food in rows]


@router.get("/queue/stats", summary="How much is waiting")
async def queue_stats(admin: AdminUser, session: SessionDep) -> dict[str, int]:
    rows = (
        await session.execute(
            select(Food.llm_verdict, func.count())
            .where(Food.review_status == ReviewStatus.PENDING)
            .group_by(Food.llm_verdict)
        )
    ).all()
    # `unscreened` is its own bucket rather than folded into a default: it means
    # the model could not be reached, which is a fact a reviewer should see.
    return {(verdict or "unscreened"): count for verdict, count in rows}


class Decision(BaseModel):
    """An admin's decision, and optionally corrections to go with it."""

    approve: bool
    #: Shown to the author. Required on a rejection: a refusal without a reason
    #: is the kind of thing that makes people stop contributing.
    note: str | None = Field(default=None, max_length=500)

    # Corrections. All optional — an admin fixing a typo in a name should not
    # have to restate the nutrition. Absent means "leave as submitted", which is
    # why every field is nullable and none has a default value.
    name: str | None = Field(default=None, min_length=1, max_length=120)
    brand: str | None = Field(default=None, max_length=120)
    kcal: float | None = Field(default=None, ge=0, le=900)
    protein_g: float | None = Field(default=None, ge=0, le=100)
    carbs_g: float | None = Field(default=None, ge=0, le=100)
    fat_g: float | None = Field(default=None, ge=0, le=100)


@router.post(
    "/foods/{food_id}/decide",
    response_model=SubmissionRead,
    summary="Approve or reject a submission",
)
async def decide(
    food_id: uuid.UUID,
    payload: Decision,
    admin: AdminUser,
    session: SessionDep,
) -> SubmissionRead:
    """Approve, with optional corrections, or reject with a reason.

    **Approval is what makes a food public**, so this is the only place in the
    codebase where one user's typing becomes visible to everybody. That is why it
    is gated on a person: the model's verdict is on the record beside this
    decision, but it never makes it.

    A rejected food stays private to its author rather than being deleted. Their
    diary references it, and leaving their history readable is worth more than
    reclaiming a row.
    """
    food = await _load(session, food_id)
    if food is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such food.")
    if food.review_status != ReviewStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That submission has already been decided.",
        )

    if not payload.approve and not (payload.note or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A rejection needs a reason the author can read.",
        )

    for field in ("name", "brand", "kcal", "protein_g", "carbs_g", "fat_g"):
        value = getattr(payload, field)
        if value is not None:
            setattr(food, field, value)

    food.review_status = ReviewStatus.APPROVED if payload.approve else ReviewStatus.REJECTED
    food.review_note = payload.note
    food.reviewed_at = datetime.now(UTC)
    food.reviewed_by = admin.id

    await session.commit()
    logger.info(
        "Food %s %s by admin %s",
        food.id,
        "approved" if payload.approve else "rejected",
        admin.id,
    )

    return _to_read(await _load(session, food.id))  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Reports — anyone can file, an admin decides
# --------------------------------------------------------------------------- #


class ReportCreate(BaseModel):
    reason: ReportReason
    #: What the label actually says, usually. Optional on purpose: requiring a
    #: paragraph is how a report button goes unused.
    note: str | None = Field(default=None, max_length=500)


class ReportedFood(BaseModel):
    """Enough of the food to judge the complaint against it.

    Not `FoodRead`: that carries portions and every optional nutrient, which a
    reviewer deciding "are these calories right" does not read. These are the
    four numbers the dispute is almost always about, plus what they can be
    checked against.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    brand: str | None
    source: str
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    withdrawn_reason: str | None

    #: Whether an admin may edit these numbers in place.
    #:
    #: False for USDA and Open Food Facts rows — `source`/`source_id` say where
    #: the figures came from, so rewriting them leaves the row claiming a
    #: provenance its numbers no longer have. Sent rather than left for the
    #: client to derive, so the admin page can hide the correction form instead
    #: of letting somebody fill it in and collect a 422.
    correctable: bool

    @property
    def kcal_implied_by_macros(self) -> float:
        """4/4/9. The single most useful check on a disputed calorie figure."""
        return 4 * self.protein_g + 4 * self.carbs_g + 9 * self.fat_g


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    food_id: uuid.UUID
    food: ReportedFood
    reason: str
    note: str | None
    status: str
    resolution: str | None
    resolution_note: str | None
    created_at: datetime
    resolved_at: datetime | None

    #: True when the importer filed this rather than a person.
    #:
    #: The two deserve different amounts of trust and different handling: a
    #: person saying "the label says 250" is evidence about the world, while
    #: "the macros do not match the stated energy" is arithmetic that is always
    #: correct about the numbers and says nothing about which of them is wrong.
    #:
    #: Read from the *reason*, not from a null `reporter_id`. A genuine report
    #: also loses its reporter when that account is deleted — `reporter_id` is
    #: SET NULL on purpose, so the evidence outlives the account — and treating
    #: those as machine-filed would quietly relabel real people's complaints.
    system: bool = False
    #: How many *distinct people* have an open report against this food. The
    #: number that decides what to look at first: five from one account is one
    #: persistent person, two from two accounts is a food that is probably wrong.
    #: Admin listings only — a reporter has no business knowing who else agreed.
    reporters: int | None = None


def _report_read(report: FoodReport, *, reporters: int | None = None) -> ReportRead:
    return ReportRead(
        id=report.id,
        food_id=report.food_id,
        food=ReportedFood(
            id=report.food.id,
            name=report.food.name,
            brand=report.food.brand,
            source=report.food.source,
            kcal=report.food.kcal,
            protein_g=report.food.protein_g,
            carbs_g=report.food.carbs_g,
            fat_g=report.food.fat_g,
            withdrawn_reason=report.food.withdrawn_reason,
            # The endpoint's own rule, mirrored so the UI can obey it up front.
            correctable=report.food.is_correctable,
        ),
        reason=report.reason,
        note=report.note,
        status=report.status,
        resolution=report.resolution,
        resolution_note=report.resolution_note,
        created_at=report.created_at,
        resolved_at=report.resolved_at,
        reporters=reporters,
        system=report.reason == ReportReason.IMPORT_CHECK,
    )


@router.post(
    "/foods/{food_id}/report",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Report a food whose numbers look wrong",
)
async def report_food(
    food_id: uuid.UUID,
    payload: ReportCreate,
    user: CurrentUser,
    session: SessionDep,
) -> ReportRead:
    """File a report. Nothing about the food changes.

    **A report is never itself a correction.** It opens a question a person
    answers — the same rule the model's screening verdict follows on the way in.
    Letting a report edit or hide a food automatically would hand anybody a way
    to delete a competitor's product from the database, and would put a nutrition
    value in the gift of whoever complained loudest.

    Reporting is allowed against any food the caller can see, including USDA and
    Open Food Facts rows. Those are the ones most worth reporting: nobody here
    typed them, so nobody here has ever checked them.
    """
    food = await _load(session, food_id)
    if food is None or not (food.is_public or food.owner_id == user.id):
        # Same 404 for "no such food" and "not visible to you", so this cannot be
        # used to confirm that somebody else's private food exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such food.")

    existing = (
        await session.execute(
            select(FoodReport).where(
                FoodReport.food_id == food_id,
                FoodReport.reporter_id == user.id,
                FoodReport.status == ReportStatus.OPEN,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        # 409 rather than silently returning the old one: the user pressed the
        # button expecting something to happen, and "you already told us" is a
        # true and useful answer. The partial unique index enforces the same rule
        # in the database, for two taps that race.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already reported this food. It is waiting to be checked.",
        )

    report = FoodReport(
        food_id=food_id,
        reporter_id=user.id,
        reason=payload.reason.value,
        note=(payload.note or "").strip() or None,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report, ["food"])

    logger.info("Food %s reported by %s (%s)", food_id, user.id, payload.reason.value)
    return _report_read(report)


@router.get(
    "/reports/mine",
    response_model=list[ReportRead],
    summary="Reports you have filed, and what came of them",
)
async def my_reports(user: CurrentUser, session: SessionDep) -> list[ReportRead]:
    """Newest first.

    This exists because a report answered with silence teaches people not to file
    another one, and the whole value of the feature is that somebody bothers.
    `resolution_note` is written for this reader.
    """
    rows = (
        (
            await session.execute(
                select(FoodReport)
                .where(FoodReport.reporter_id == user.id)
                .options(selectinload(FoodReport.food))
                .order_by(FoodReport.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_report_read(report) for report in rows]


@router.get(
    "/reports",
    response_model=list[ReportRead],
    summary="Open reports, most-disputed first",
)
async def report_queue(
    admin: AdminUser,
    session: SessionDep,
    reason: Annotated[ReportReason | None, Query(description="Filter by reason")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ReportRead]:
    """Ordered by how many distinct people are complaining, then by age.

    Not oldest-first like the submission queue, and the difference is deliberate.
    A submission is one person waiting on an answer, so making them wait longer
    than everyone else is the unfairness to avoid. A report is about a number
    other people are reading *right now*, so the food several people flagged is
    the one costing the most to leave alone.
    """
    reporters = (
        select(
            FoodReport.food_id.label("food_id"),
            func.count(func.distinct(FoodReport.reporter_id)).label("reporters"),
        )
        .where(FoodReport.status == ReportStatus.OPEN)
        .group_by(FoodReport.food_id)
        .subquery()
    )

    query = (
        select(FoodReport, reporters.c.reporters)
        .join(reporters, reporters.c.food_id == FoodReport.food_id)
        .where(FoodReport.status == ReportStatus.OPEN)
        .options(selectinload(FoodReport.food))
        .order_by(reporters.c.reporters.desc(), FoodReport.created_at)
        .limit(limit)
    )
    if reason is not None:
        query = query.where(FoodReport.reason == reason.value)

    rows = (await session.execute(query)).all()
    return [_report_read(report, reporters=count) for report, count in rows]


class ReportDecision(BaseModel):
    """What an admin decides about a reported food."""

    #: False dismisses it: checked, and the food stands.
    accept: bool
    #: What was done. Required when accepting — see `ReportResolution`. Ignored
    #: on a dismissal, where the answer is that nothing was done.
    resolution: ReportResolution | None = None
    #: Shown to everyone who reported this food.
    note: str | None = Field(default=None, max_length=500)

    # Corrections, applied only with `resolution=corrected`. Same shape as
    # `Decision` above: absent means "leave as it is".
    name: str | None = Field(default=None, min_length=1, max_length=120)
    brand: str | None = Field(default=None, max_length=120)
    kcal: float | None = Field(default=None, ge=0, le=900)
    protein_g: float | None = Field(default=None, ge=0, le=100)
    carbs_g: float | None = Field(default=None, ge=0, le=100)
    fat_g: float | None = Field(default=None, ge=0, le=100)


@router.post(
    "/reports/{report_id}/resolve",
    response_model=list[ReportRead],
    summary="Decide a report, closing every open report on that food",
)
async def resolve_report(
    report_id: uuid.UUID,
    payload: ReportDecision,
    admin: AdminUser,
    session: SessionDep,
) -> list[ReportRead]:
    """One decision, applied to every open report against the same food.

    **Why it closes them all.** The decision is about the food, not about who
    said so. Resolving one at a time would leave the other four in the queue
    describing a problem already fixed — and the next admin through would look at
    a corrected food and dismiss a report that had been entirely right.

    **Correcting is only legitimate for a food a user wrote.** The numbers on a
    USDA or Open Food Facts row belong to that source, and `source`/`source_id`
    say so — editing them in place would leave a row claiming a provenance its
    figures no longer have, which is the one thing this codebase does not do.
    When one of those is wrong the answer is `withdrawn`, and the fix belongs
    upstream.
    """
    report = (
        await session.execute(
            select(FoodReport)
            .where(FoodReport.id == report_id)
            .options(selectinload(FoodReport.food))
        )
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such report.")
    if report.status != ReportStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That report has already been decided.",
        )

    food = await _load(session, report.food_id)
    if food is None:  # pragma: no cover - the foreign key cascades, so this cannot happen
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such food.")

    if payload.accept:
        if payload.resolution is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Accepting a report needs a resolution: corrected, or withdrawn.",
            )
        if payload.resolution is ReportResolution.CORRECTED and not food.is_correctable:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"This food's numbers come from {food.source}, which we re-fetch — "
                    "an edit here is overwritten on the next refresh, and until then "
                    "the row claims a source its figures no longer have. Withdraw it "
                    "instead, and report the error upstream."
                ),
            )

        if payload.resolution is ReportResolution.CORRECTED:
            for field in ("name", "brand", "kcal", "protein_g", "carbs_g", "fat_g"):
                value = getattr(payload, field)
                if value is not None:
                    setattr(food, field, value)
            food.withdrawn_at = None
            food.withdrawn_reason = None
            if food.owner_id is not None:
                food.review_status = ReviewStatus.APPROVED
        else:
            food.withdrawn_at = datetime.now(UTC)
            food.withdrawn_reason = payload.note

    open_reports = (
        (
            await session.execute(
                select(FoodReport)
                .where(
                    FoodReport.food_id == report.food_id,
                    FoodReport.status == ReportStatus.OPEN,
                )
                .options(selectinload(FoodReport.food))
            )
        )
        .scalars()
        .all()
    )

    now = datetime.now(UTC)
    for each in open_reports:
        each.status = ReportStatus.ACCEPTED if payload.accept else ReportStatus.DISMISSED
        each.resolution = payload.resolution.value if payload.accept else None
        each.resolution_note = payload.note
        each.resolved_at = now
        each.resolved_by = admin.id

    await session.commit()
    logger.info(
        "Report %s on food %s %s by admin %s (%d report(s) closed)",
        report_id,
        report.food_id,
        f"accepted as {payload.resolution}" if payload.accept else "dismissed",
        admin.id,
        len(open_reports),
    )

    for each in open_reports:
        await session.refresh(each, ["food"])
    return [_report_read(each) for each in open_reports]


# --------------------------------------------------------------------------- #
# Inventory — what is in the database, and what it is still missing
# --------------------------------------------------------------------------- #


class FoodNote(BaseModel):
    """One food, as the notes tab lists it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    name_fr: str | None
    source: str
    kind: str
    kcal: float
    has_photo: bool
    portions: int
    withdrawn: bool


class Inventory(BaseModel):
    """The state of the food database, and every food in it by name.

    Exists because the questions it answers were previously only answerable by
    writing SQL: how many foods are there, how many still have no photograph,
    which ones can nobody log in sensible units. Those are the questions that
    decide what to work on next, so they should not need a database client.
    """

    foods_total: int
    by_source: dict[str, int]
    with_photo: int
    with_portions: int
    missing_photo: int
    missing_portions: int
    pending_submissions: int
    open_reports: int
    import_flags: int
    #: Foods whose serving size is deliberately blank. See
    #: `services/portions_maghreb.WANTED` — every one varies by bakery, region
    #: or household, and a plausible-looking guess would be an invented number
    #: that silently scales every nutrient on the row.
    portions_wanted: list[str]
    foods: list[FoodNote]


@router.get(
    "/inventory",
    response_model=Inventory,
    summary="Every food by name, and what it is still missing",
)
async def inventory(
    admin: AdminUser,
    session: SessionDep,
    missing_photo: Annotated[bool, Query(description="Only foods with no photograph")] = False,
) -> Inventory:
    """Everything at once, filtered in the browser rather than by re-querying.

    A few thousand compact rows is a smaller payload than the photographs on one
    screen of the app, and having the whole list client-side makes searching it
    instant — which matters when the job is "find the foods that still need a
    photo" and the answer is a few hundred names.
    """
    from app.services.portions_maghreb import WANTED

    portion_counts = (
        select(FoodPortion.food_id, func.count().label("n"))
        .group_by(FoodPortion.food_id)
        .subquery()
    )

    rows = (
        await session.execute(
            select(Food, func.coalesce(portion_counts.c.n, 0))
            .outerjoin(portion_counts, portion_counts.c.food_id == Food.id)
            .order_by(Food.source, Food.name)
        )
    ).all()

    foods = [
        FoodNote(
            id=food.id,
            name=food.name,
            name_fr=food.name_fr,
            source=food.source,
            kind=food.kind,
            kcal=food.kcal,
            has_photo=food.photo is not None,
            portions=count,
            withdrawn=food.withdrawn_at is not None,
        )
        for food, count in rows
    ]

    by_source: dict[str, int] = {}
    for note in foods:
        by_source[note.source] = by_source.get(note.source, 0) + 1

    pending = (
        await session.execute(
            select(func.count()).select_from(Food).where(Food.review_status == ReviewStatus.PENDING)
        )
    ).scalar_one()
    open_reports = (
        await session.execute(
            select(func.count())
            .select_from(FoodReport)
            .where(FoodReport.status == ReportStatus.OPEN)
        )
    ).scalar_one()
    flags = (
        await session.execute(
            select(func.count())
            .select_from(FoodReport)
            .where(
                FoodReport.status == ReportStatus.OPEN,
                FoodReport.reason == ReportReason.IMPORT_CHECK,
            )
        )
    ).scalar_one()

    return Inventory(
        foods_total=len(foods),
        by_source=by_source,
        with_photo=sum(1 for f in foods if f.has_photo),
        with_portions=sum(1 for f in foods if f.portions),
        missing_photo=sum(1 for f in foods if not f.has_photo),
        missing_portions=sum(1 for f in foods if not f.portions),
        pending_submissions=pending,
        open_reports=open_reports,
        import_flags=flags,
        portions_wanted=list(WANTED),
        foods=[f for f in foods if not f.has_photo] if missing_photo else foods,
    )


class FoodEditInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    brand: str | None = Field(default=None, max_length=120)
    kcal: float | None = Field(default=None, ge=0, le=900)
    protein_g: float | None = Field(default=None, ge=0, le=100)
    carbs_g: float | None = Field(default=None, ge=0, le=100)
    fat_g: float | None = Field(default=None, ge=0, le=100)
    republish: bool = Field(default=True, description="Restore to active search index")


@router.post(
    "/foods/{food_id}/edit",
    response_model=FoodRead,
    summary="Directly edit and republish a food entry as an admin",
)
async def edit_food(
    food_id: uuid.UUID,
    payload: FoodEditInput,
    admin: AdminUser,
    session: SessionDep,
) -> FoodRead:
    """Edit food numbers in place and republish it."""
    food = await _load(session, food_id)
    if food is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such food.")

    if not food.is_correctable:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"This food's numbers come from {food.source}, which cannot be edited directly.",
        )

    for field in ("name", "brand", "kcal", "protein_g", "carbs_g", "fat_g"):
        value = getattr(payload, field)
        if value is not None:
            setattr(food, field, value)

    if payload.republish:
        food.withdrawn_at = None
        food.withdrawn_reason = None
        if food.owner_id is not None:
            food.review_status = ReviewStatus.APPROVED

    await session.commit()
    logger.info("Food %s edited and republished by admin %s", food.id, admin.id)
    return FoodRead.model_validate(await _load(session, food.id))

