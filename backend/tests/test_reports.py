"""Reporting a food whose numbers are wrong.

The other direction from `test_review.py`. That file guards the way in — nothing
becomes public without a person. This one guards what happens to something
already in, and the property it protects is the mirror image:

**A report never changes a food by itself.** If it could, anyone would have a
button that edits a nutrition value or deletes a competitor's product, and the
number would belong to whoever complained loudest rather than to a source.

Two rules get the most tests, because both are easy to lose in a later refactor
that looks like a simplification:

* filing a report leaves the food untouched, and
* an admin cannot "correct" a USDA or Open Food Facts row — the numbers are that
  source's, and `source`/`source_id` say so, so editing them in place would
  leave a row claiming a provenance its figures no longer have.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.db.models.food import (
    Food,
    FoodKind,
    FoodReport,
    FoodSource,
    ReportReason,
    ReportStatus,
)
from app.db.models.user import User

PASSWORD = "correct-horse-battery"

#: Enough of a profile for the diary to resolve a local day.
PROFILE = {
    "sex": "male",
    "birth_date": "1996-05-20",
    "height_cm": 180,
    "weight_kg": 80,
    "activity_level": "moderate",
    "goal": "maintain",
    "timezone": "UTC",
}


def account(client: TestClient, email: str) -> dict[str, str]:
    """Register, or sign in if the address already exists."""
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    if response.status_code != 201:
        response = client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def admin_account(client: TestClient, session, email: str) -> dict[str, str]:
    account(client, email)
    await session.execute(update(User).where(User.email == email).values(is_admin=True))
    await session.commit()
    return account(client, email)


def add_food(client: TestClient, headers: dict[str, str], name: str = "Zzqx Bar") -> str:
    """A food the caller owns. Private until submitted, which is fine here."""
    created = client.post(
        "/api/v1/foods",
        headers=headers,
        json={"name": name, "kcal": 400, "protein_g": 10, "carbs_g": 50, "fat_g": 15},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def upstream_food(session, name: str = "Yoghurt, plain") -> uuid.UUID:
    """A row with no owner, as USDA and Open Food Facts rows are.

    Written directly rather than through the API because there is no endpoint
    that creates one — which is the point. These arrive from an importer, and
    nothing in the app is allowed to author them.
    """
    food = Food(
        source=FoodSource.OFF,
        source_id=f"off:{uuid.uuid4().hex[:12]}",
        name=name,
        kcal=61,
        protein_g=3.5,
        carbs_g=4.7,
        fat_g=3.3,
    )
    session.add(food)
    await session.commit()
    return food.id


def report(
    client: TestClient,
    headers: dict[str, str],
    food_id,
    reason: str = "wrong_numbers",
    note: str | None = "The pack says 250 kcal per 100 g.",
):
    return client.post(
        f"/api/v1/review/foods/{food_id}/report",
        headers=headers,
        json={"reason": reason, "note": note},
    )


# --------------------------------------------------------------------------- #
# Filing
# --------------------------------------------------------------------------- #


def test_reporting_a_food_you_can_see(client: TestClient) -> None:
    headers = account(client, "reporter@example.com")
    food_id = add_food(client, headers)

    response = report(client, headers, food_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "open"
    assert body["reason"] == "wrong_numbers"
    assert body["food"]["name"] == "Zzqx Bar"
    assert body["resolution"] is None


async def test_a_report_changes_nothing_about_the_food(client: TestClient, session) -> None:
    """The property the whole feature rests on.

    A report that could edit or hide a food on its own would hand anybody a way
    to delete a competitor's product, and would put a nutrition value in the
    gift of whoever complained loudest.
    """
    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session)

    assert report(client, headers, food_id).status_code == 201

    food = (await session.execute(select(Food).where(Food.id == food_id))).scalar_one()
    await session.refresh(food)
    assert float(food.kcal) == 61
    assert food.withdrawn_at is None
    assert food.is_public


async def test_upstream_rows_are_reportable(client: TestClient, session) -> None:
    """USDA and Open Food Facts rows are the ones most worth reporting.

    Nobody here typed them, so nobody here has ever checked them. A report flow
    that only covered user-submitted foods would miss almost every wrong number
    in the database — and those rows have no owner, so the visibility check has
    to let them through on `is_public` rather than on ownership.
    """
    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session)

    assert report(client, headers, food_id).status_code == 201


async def test_reporting_the_same_food_twice_is_refused(client: TestClient, session) -> None:
    """409, not a silent second row.

    Ten reports from one account would otherwise look like ten people
    disagreeing, and the admin queue sorts on exactly that number.
    """
    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session)

    assert report(client, headers, food_id).status_code == 201
    second = report(client, headers, food_id)

    assert second.status_code == 409
    assert "already reported" in second.json()["detail"]


async def test_two_people_can_report_the_same_food(client: TestClient, session) -> None:
    food_id = await upstream_food(session)

    first = account(client, "one@example.com")
    second = account(client, "two@example.com")

    assert report(client, first, food_id).status_code == 201
    assert report(client, second, food_id).status_code == 201


def test_cannot_report_somebody_elses_private_food(client: TestClient) -> None:
    """404, the same answer as a food that does not exist.

    A 403 would confirm the id is real, which is a way to enumerate other
    people's private foods one guess at a time.
    """
    author = account(client, "author@example.com")
    food_id = add_food(client, author, name="Secret Recipe")

    stranger = account(client, "stranger@example.com")
    response = report(client, stranger, food_id)

    assert response.status_code == 404


def test_reporting_needs_a_reason(client: TestClient) -> None:
    headers = account(client, "reporter@example.com")
    food_id = add_food(client, headers)

    response = client.post(
        f"/api/v1/review/foods/{food_id}/report", headers=headers, json={"note": "wrong"}
    )
    assert response.status_code == 422


def test_reporting_requires_a_signed_in_account(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/review/foods/{uuid.uuid4()}/report", json={"reason": "other"}
    )
    assert response.status_code == 401


def test_a_note_is_optional(client: TestClient) -> None:
    """Requiring a paragraph is how a report button goes unused."""
    headers = account(client, "reporter@example.com")
    food_id = add_food(client, headers)

    response = report(client, headers, food_id, note=None)

    assert response.status_code == 201
    assert response.json()["note"] is None


def test_a_blank_note_is_stored_as_null(client: TestClient) -> None:
    """So "  " and "" do not read differently from having said nothing."""
    headers = account(client, "reporter@example.com")
    food_id = add_food(client, headers)

    assert report(client, headers, food_id, note="   ").json()["note"] is None


# --------------------------------------------------------------------------- #
# The reporter's own list
# --------------------------------------------------------------------------- #


def test_my_reports_lists_what_you_filed(client: TestClient) -> None:
    headers = account(client, "reporter@example.com")
    report(client, headers, add_food(client, headers, "One"))
    report(client, headers, add_food(client, headers, "Two"))

    rows = client.get("/api/v1/review/reports/mine", headers=headers).json()

    assert {row["food"]["name"] for row in rows} == {"One", "Two"}


def test_my_reports_shows_only_your_own(client: TestClient) -> None:
    mine = account(client, "mine@example.com")
    theirs = account(client, "theirs@example.com")
    report(client, theirs, add_food(client, theirs, "Not Yours"))
    report(client, mine, add_food(client, mine, "Yours"))

    rows = client.get("/api/v1/review/reports/mine", headers=mine).json()

    assert [row["food"]["name"] for row in rows] == ["Yours"]


# --------------------------------------------------------------------------- #
# The admin queue
# --------------------------------------------------------------------------- #


async def test_the_queue_is_admin_only(client: TestClient, session) -> None:
    """404 rather than 403, so the admin surface is not mapped by probing."""
    headers = account(client, "ordinary@example.com")
    assert client.get("/api/v1/review/reports", headers=headers).status_code == 404


async def test_queue_orders_by_how_many_people_are_complaining(
    client: TestClient, session
) -> None:
    """Not oldest-first, unlike the submission queue.

    A submission is one person waiting; a report is about a number other people
    are reading right now. The food two people flagged costs more to leave alone
    than the one person flagged first.
    """
    quiet = await upstream_food(session, "Quiet Food")
    disputed = await upstream_food(session, "Disputed Food")

    first = account(client, "one@example.com")
    second = account(client, "two@example.com")

    report(client, first, quiet)  # oldest
    report(client, first, disputed)
    report(client, second, disputed)

    admin = await admin_account(client, session, "admin@example.com")
    rows = client.get("/api/v1/review/reports", headers=admin).json()

    assert rows[0]["food"]["name"] == "Disputed Food"
    assert rows[0]["reporters"] == 2


async def test_queue_filters_by_reason(client: TestClient, session) -> None:
    headers = account(client, "reporter@example.com")
    report(client, headers, await upstream_food(session, "A"), reason="wrong_numbers")
    report(client, headers, await upstream_food(session, "B"), reason="duplicate")

    admin = await admin_account(client, session, "admin@example.com")
    rows = client.get(
        "/api/v1/review/reports", headers=admin, params={"reason": "duplicate"}
    ).json()

    assert [row["food"]["name"] for row in rows] == ["B"]


# --------------------------------------------------------------------------- #
# Deciding
# --------------------------------------------------------------------------- #


async def test_accepting_with_a_correction_edits_a_user_food(
    client: TestClient, session
) -> None:
    author = account(client, "author@example.com")
    food_id = add_food(client, author)
    report(client, author, food_id)

    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]

    response = client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=admin,
        json={"accept": True, "resolution": "corrected", "kcal": 250, "note": "Fixed."},
    )

    assert response.status_code == 200, response.text
    food = (
        await session.execute(select(Food).where(Food.id == uuid.UUID(food_id)))
    ).scalar_one()
    await session.refresh(food)
    assert float(food.kcal) == 250
    assert food.withdrawn_at is None


async def test_an_upstream_food_cannot_be_corrected(client: TestClient, session) -> None:
    """The rule this whole feature had to be designed around.

    `source` and `source_id` say the numbers came from Open Food Facts. Editing
    them in place leaves a row claiming a provenance its figures no longer have —
    which is the one thing this codebase does not do. The answer is to withdraw
    it and fix the error upstream.
    """
    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session)
    report(client, headers, food_id)

    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]

    response = client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=admin,
        json={"accept": True, "resolution": "corrected", "kcal": 250},
    )

    assert response.status_code == 422
    assert "which we re-fetch" in response.json()["detail"]

    food = (await session.execute(select(Food).where(Food.id == food_id))).scalar_one()
    await session.refresh(food)
    assert float(food.kcal) == 61, "the refusal must not have edited anything"


async def test_withdrawing_takes_a_food_out_of_search(client: TestClient, session) -> None:
    """Against `search_local` rather than the endpoint, on purpose.

    `/foods/search` falls through to USDA, so driving this over HTTP would put a
    network call in the middle of a test about a WHERE clause — slow, and able to
    fail for a reason that has nothing to do with what is being checked.
    """
    from app.services.food_cache import search_local

    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session, "Zzqxyoghurt Plain")
    report(client, headers, food_id)

    before = await search_local(session, "Zzqxyoghurt", limit=10, owner_id=None)
    assert [food.id for food in before] == [food_id], "seed check: it was findable"

    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]
    client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=admin,
        json={"accept": True, "resolution": "withdrawn", "note": "Label says 95 kcal."},
    )

    after = await search_local(session, "Zzqxyoghurt", limit=10, owner_id=None)
    assert after == []


async def test_a_withdrawn_food_is_still_readable(client: TestClient, session) -> None:
    """Withdrawal is not deletion, and the difference matters.

    A wrong food is usually already in somebody's diary. Deleting the row would
    take that history with it; a past entry is a record of what was logged, not
    a number the app is still claiming. So the food stays fetchable and says why.
    """
    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session)
    report(client, headers, food_id)

    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]
    client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=admin,
        json={"accept": True, "resolution": "withdrawn", "note": "Label says 95 kcal."},
    )

    detail = client.get(f"/api/v1/foods/{food_id}", headers=headers)

    assert detail.status_code == 200
    assert detail.json()["withdrawn_reason"] == "Label says 95 kcal."


async def test_one_decision_closes_every_open_report_on_that_food(
    client: TestClient, session
) -> None:
    """Otherwise the next admin through sees a report about a fixed food.

    They would look at corrected numbers, find nothing wrong, and dismiss a
    report that had been entirely right.
    """
    food_id = await upstream_food(session)
    first = account(client, "one@example.com")
    second = account(client, "two@example.com")
    report(client, first, food_id)
    report(client, second, food_id)

    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]
    response = client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=admin,
        json={"accept": True, "resolution": "withdrawn", "note": "Wrong."},
    )

    assert len(response.json()) == 2
    assert client.get("/api/v1/review/reports", headers=admin).json() == []


async def test_dismissing_leaves_the_food_alone(client: TestClient, session) -> None:
    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session)
    report(client, headers, food_id)

    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]
    response = client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=admin,
        json={"accept": False, "note": "Checked against the label; it matches."},
    )

    assert response.status_code == 200
    assert response.json()[0]["status"] == "dismissed"
    assert response.json()[0]["resolution"] is None

    food = (await session.execute(select(Food).where(Food.id == food_id))).scalar_one()
    await session.refresh(food)
    assert food.withdrawn_at is None


async def test_accepting_needs_a_resolution(client: TestClient, session) -> None:
    """Acceptance alone does not say whether a number changed.

    For a food whose figures came from USDA the honest answer is usually that
    none did, and the record has to be able to say so — hence `resolution`.
    """
    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session)
    report(client, headers, food_id)

    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]

    response = client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=admin,
        json={"accept": True, "note": "Yes, wrong."},
    )
    assert response.status_code == 422


async def test_a_decided_report_cannot_be_decided_again(client: TestClient, session) -> None:
    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session)
    report(client, headers, food_id)

    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]
    body = {"accept": False, "note": "Fine."}
    assert client.post(
        f"/api/v1/review/reports/{report_id}/resolve", headers=admin, json=body
    ).status_code == 200

    again = client.post(
        f"/api/v1/review/reports/{report_id}/resolve", headers=admin, json=body
    )
    assert again.status_code == 409


async def test_resolving_is_admin_only(client: TestClient, session) -> None:
    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session)
    report_id = report(client, headers, food_id).json()["id"]

    response = client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=headers,
        json={"accept": True, "resolution": "withdrawn", "note": "Mine now."},
    )
    assert response.status_code == 404


async def test_the_reporter_sees_what_came_of_it(client: TestClient, session) -> None:
    """A report answered with silence teaches people not to file another one."""
    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session)
    report(client, headers, food_id)

    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]
    client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=admin,
        json={"accept": True, "resolution": "withdrawn", "note": "You were right."},
    )

    mine = client.get("/api/v1/review/reports/mine", headers=headers).json()

    assert mine[0]["status"] == "accepted"
    assert mine[0]["resolution"] == "withdrawn"
    assert mine[0]["resolution_note"] == "You were right."


async def test_reporting_again_after_a_decision_is_allowed(
    client: TestClient, session
) -> None:
    """The unique index is partial on `status = 'open'`, and that is deliberate.

    A fix that did not work is a legitimate second report. A blanket unique
    constraint would silence it forever.
    """
    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session)
    report(client, headers, food_id)

    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]
    client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=admin,
        json={"accept": False, "note": "Looks right to me."},
    )

    assert report(client, headers, food_id).status_code == 201


@pytest.mark.parametrize(
    "reason", ["wrong_numbers", "wrong_name", "not_food", "duplicate", "other"]
)
def test_every_reason_the_app_offers_is_accepted(client: TestClient, reason: str) -> None:
    """Guards the enum against the mobile client drifting away from it.

    `REPORT_REASONS` in `mobile/src/api/review.ts` is this list. A value the
    sheet offers and the API rejects is a button that always fails.
    """
    headers = account(client, "reporter@example.com")
    food_id = add_food(client, headers, name=f"Food {reason}")

    assert report(client, headers, food_id, reason=reason).status_code == 201


async def test_a_withdrawn_catalogue_food_leaves_the_browse_screen(
    client: TestClient, session
) -> None:
    """Search is not the only way in. The catalogue is a second query.

    Filtering one and forgetting the other is exactly the kind of gap that ships:
    the food vanishes from the place you tested and stays on the place you did
    not.
    """
    from app.services.catalogue import _catalogue_query

    food = Food(
        source=FoodSource.USDA,
        source_id=f"usda:{uuid.uuid4().hex[:12]}",
        kind=FoodKind.CATALOGUE,
        # Both required by the `catalogue_complete` check constraint: a
        # catalogue row without a slug can never be looked up and one without a
        # category can never be grouped into a section, so the database refuses
        # them rather than letting the food silently not appear.
        slug=f"zzqx-{uuid.uuid4().hex[:8]}",
        category="protein",
        name="Zzqx Catalogue Item",
        kcal=100,
        protein_g=1,
        carbs_g=2,
        fat_g=3,
    )
    session.add(food)
    await session.commit()

    before = (await session.execute(_catalogue_query())).scalars().all()
    assert food.id in {row.id for row in before}, "seed check: it was on the list"

    food.withdrawn_at = datetime.now(UTC)
    await session.commit()

    after = (await session.execute(_catalogue_query())).scalars().all()
    assert food.id not in {row.id for row in after}


async def test_a_withdrawn_food_leaves_quick_add(client: TestClient, session) -> None:
    """The third place a withdrawn food has to disappear from.

    Easy to miss, because these rows come from the user's own diary rather than
    from a lookup — but it is still a list of one-tap suggestions, and offering
    a food we upheld a report against is offering it again.
    """
    headers = account(client, "reporter@example.com")
    # Logging resolves "today" from the profile's timezone, so the account needs
    # one before the diary will accept an entry.
    client.put("/api/v1/profile", headers=headers, json=PROFILE)

    food_id = await upstream_food(session, "Zzqx Quickadd")
    logged = client.post(
        "/api/v1/diary",
        headers=headers,
        json={"food_id": str(food_id), "meal_slot": "lunch", "quantity_grams": 100},
    )
    assert logged.status_code == 201, logged.text

    before = client.get("/api/v1/foods/quick-add", headers=headers).json()
    assert any(row["id"] == str(food_id) for row in before), "seed check: it was offered"

    report(client, headers, food_id)
    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]
    client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=admin,
        json={"accept": True, "resolution": "withdrawn", "note": "Wrong."},
    )

    after = client.get("/api/v1/foods/quick-add", headers=headers).json()
    assert not any(row["id"] == str(food_id) for row in after)


async def test_the_reported_foods_view_shows_what_a_reviewer_needs(
    client: TestClient, session
) -> None:
    """The view Supabase Studio is pointed at — the actual triage interface.

    Tested for the same reason as `review_queue`: an untested view is an admin
    tool that breaks silently the next time a column is renamed.
    """
    from sqlalchemy import text as sql

    food_id = await upstream_food(session, "Zzqx Reportview")
    first = account(client, "one@example.com")
    second = account(client, "two@example.com")
    report(client, first, food_id, reason="wrong_numbers", note="Pack says 250.")
    report(client, second, food_id, reason="duplicate", note=None)

    row = (
        (
            await session.execute(
                sql("SELECT * FROM reported_foods WHERE name = 'Zzqx Reportview'")
            )
        )
        .mappings()
        .one()
    )

    assert row["reporters"] == 2
    assert row["reports"] == 2
    assert row["reasons"] == "duplicate, wrong_numbers"
    assert "Pack says 250." in row["notes"]
    # 4*3.5 + 4*4.7 + 9*3.3 = 62.5, against 61 declared. The arithmetic a
    # reviewer would otherwise do by hand, and get wrong.
    assert row["kcal_implied_by_macros"] == 63
    assert row["withdrawn_at"] is None


async def test_a_resolved_report_leaves_the_view(client: TestClient, session) -> None:
    from sqlalchemy import text as sql

    headers = account(client, "reporter@example.com")
    food_id = await upstream_food(session, "Zzqx Leaves")
    report(client, headers, food_id)

    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]
    client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=admin,
        json={"accept": False, "note": "Matches the source."},
    )

    remaining = (
        await session.execute(
            sql("SELECT count(*) FROM reported_foods WHERE name = 'Zzqx Leaves'")
        )
    ).scalar_one()
    assert remaining == 0


async def test_deleting_the_reporter_keeps_the_report(client: TestClient, session) -> None:
    """SET NULL, not CASCADE.

    A report is evidence about a food, and it stays true after the person who
    filed it deletes their account.
    """
    headers = account(client, "leaver@example.com")
    food_id = await upstream_food(session)
    report(client, headers, food_id)

    user = (
        await session.execute(select(User).where(User.email == "leaver@example.com"))
    ).scalar_one()
    await session.delete(user)
    await session.commit()

    rows = (
        (await session.execute(select(FoodReport).where(FoodReport.food_id == food_id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].reporter_id is None
    assert rows[0].status == ReportStatus.OPEN


# --------------------------------------------------------------------------- #
# Which foods an admin may correct
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("source", "correctable"),
    [
        # Live upstreams we re-fetch. An edit is overwritten on the next refresh
        # and, until then, leaves a row claiming a provenance its figures no
        # longer have.
        (FoodSource.USDA, False),
        (FoodSource.OFF, False),
        # Static tables imported once and never re-fetched. When a reviewer
        # opens INNTA page 31, reads the real figure and types it in, that is
        # restoring what the table says — the OCR was the error, not the table.
        # Forbidding it would mean the only remedy for a mistyped Tunisian food
        # is deleting it from an app whose whole point is having those foods.
        (FoodSource.INNTA, True),
        (FoodSource.CIQUAL, True),
        (FoodSource.USER, True),
    ],
)
def test_which_sources_an_admin_may_correct(source: str, correctable: bool) -> None:
    assert Food(source=source, source_id="x", name="n").is_correctable is correctable


async def test_an_innta_row_can_be_corrected_against_the_printed_table(
    client: TestClient, session
) -> None:
    """The workflow the import flagging exists to serve.

    An OCR error is found, a reviewer checks the page, and types the real
    number. Before `is_correctable` looked at the *source* rather than at
    ownership, this returned 422 and the only remedy was withdrawal.
    """
    food = Food(
        source=FoodSource.INNTA,
        source_id=f"innta-{uuid.uuid4().hex[:6]}",
        name="Œuf, frais",
        name_fr="Œuf, frais",
        kcal=147,
        protein_g=12.58,
        carbs_g=13.52,
        fat_g=9.94,
    )
    session.add(food)
    await session.commit()

    headers = account(client, "reporter@example.com")
    report(client, headers, food.id, reason="wrong_numbers", note="Eggs have no carbs.")

    admin = await admin_account(client, session, "admin@example.com")
    report_id = client.get("/api/v1/review/reports", headers=admin).json()[0]["id"]
    response = client.post(
        f"/api/v1/review/reports/{report_id}/resolve",
        headers=admin,
        json={
            "accept": True,
            "resolution": "corrected",
            "carbs_g": 0.7,
            "note": "Checked INNTA page 77; the carbohydrate column was mis-read.",
        },
    )

    assert response.status_code == 200, response.text
    await session.refresh(food)
    assert float(food.carbs_g) == 0.7


async def test_import_flags_are_marked_as_machine_filed(client: TestClient, session) -> None:
    """The console shows these differently, and it needs a signal to do it on.

    Read from the reason rather than a null reporter: a genuine report also
    loses its reporter when that account is deleted.
    """
    food_id = await upstream_food(session, "Zzqx Flagged")
    session.add(
        FoodReport(
            food_id=food_id,
            reporter_id=None,
            reason=ReportReason.IMPORT_CHECK,
            note="States 147 kcal, macros imply 194.",
        )
    )
    await session.commit()

    admin = await admin_account(client, session, "admin@example.com")
    rows = client.get("/api/v1/review/reports", headers=admin).json()

    assert rows[0]["system"] is True


async def test_a_real_report_is_not_marked_as_machine_filed(
    client: TestClient, session
) -> None:
    """Even after the reporter deletes their account.

    `reporter_id` is SET NULL on purpose so the evidence outlives the account;
    reading `system` off that would quietly relabel real people's complaints as
    arithmetic.
    """
    headers = account(client, "leaver@example.com")
    food_id = await upstream_food(session)
    report(client, headers, food_id)

    user = (
        await session.execute(select(User).where(User.email == "leaver@example.com"))
    ).scalar_one()
    await session.delete(user)
    await session.commit()

    admin = await admin_account(client, session, "admin@example.com")
    rows = client.get("/api/v1/review/reports", headers=admin).json()

    assert rows[0]["reason"] == "wrong_numbers"
    assert rows[0]["system"] is False
