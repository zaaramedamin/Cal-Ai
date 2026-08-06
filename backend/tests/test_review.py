"""The food submission pipeline.

The single most important property here: **approval is the only route by which
one user's typing becomes visible to another**, and it runs through a person. The
model sorts the queue; it never decides. Most of these tests exist to hold that
line.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.api.v1.review import get_reviewer
from app.db.models.user import User
from app.main import app
from app.services.food_review import ReviewOpinion


class StubReviewer:
    """Returns a fixed opinion, and records that it was asked."""

    def __init__(self, opinion: ReviewOpinion | None) -> None:
        self.opinion = opinion
        self.calls = 0

    async def assess(self, food) -> ReviewOpinion | None:  # noqa: ANN001
        self.calls += 1
        return self.opinion


def use_reviewer(opinion: ReviewOpinion | None) -> StubReviewer:
    stub = StubReviewer(opinion)
    app.dependency_overrides[get_reviewer] = lambda: stub
    return stub


@pytest.fixture(autouse=True)
def _clear_override():
    yield
    app.dependency_overrides.pop(get_reviewer, None)


PASSWORD = "correct-horse-battery"


def account(client: TestClient, email: str) -> dict[str, str]:
    """Register, or sign in if the address is already taken.

    Needed because promoting someone to admin happens *after* they exist, so a
    test naturally asks for the same account twice.
    """
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    if response.status_code != 201:
        response = client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def admin_account(client: TestClient, session, email: str) -> dict[str, str]:
    """An account with the admin flag set, signed in."""
    account(client, email)
    await session.execute(update(User).where(User.email == email).values(is_admin=True))
    await session.commit()
    return account(client, email)


def add_food(client: TestClient, headers: dict[str, str], name: str = "Zzqx Bar") -> str:
    created = client.post(
        "/api/v1/foods",
        headers=headers,
        json={"name": name, "kcal": 400, "protein_g": 10, "carbs_g": 50, "fat_g": 15},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


PLAUSIBLE = ReviewOpinion(verdict="plausible", reason="Looks like a cereal bar.")


# --------------------------------------------------------------------------- #
# Submission
# --------------------------------------------------------------------------- #


async def test_a_submitted_food_is_still_not_public(client: TestClient) -> None:
    """Submitting is asking, not publishing. Until a human approves it, nobody
    else can see it — which is the whole reason the queue exists."""
    use_reviewer(PLAUSIBLE)
    mine = account(client, "author@example.com")
    food_id = add_food(client, mine)

    submitted = client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["review_status"] == "pending"

    stranger = account(client, "stranger@example.com")
    results = client.get("/api/v1/foods/search?q=Zzqx", headers=stranger).json()
    assert results["results"] == []


async def test_the_author_keeps_using_their_food_while_it_waits(client: TestClient) -> None:
    """Waiting for approval to log your own lunch would be absurd."""
    use_reviewer(PLAUSIBLE)
    mine = account(client, "waiting@example.com")
    food_id = add_food(client, mine)
    client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)

    own = client.get("/api/v1/foods/search?q=Zzqx", headers=mine).json()
    assert [r["id"] for r in own["results"]] == [food_id]


async def test_screening_failure_does_not_block_a_submission(client: TestClient) -> None:
    """An outage at Google must not be able to stop people contributing. The
    food is queued unscreened and a human still sees it."""
    use_reviewer(None)
    mine = account(client, "unscreened@example.com")
    food_id = add_food(client, mine)

    body = client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine).json()

    assert body["review_status"] == "pending"
    assert body["llm_verdict"] is None


async def test_a_food_cannot_be_submitted_twice(client: TestClient) -> None:
    use_reviewer(PLAUSIBLE)
    mine = account(client, "twice@example.com")
    food_id = add_food(client, mine)

    client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)
    again = client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)

    assert again.status_code == 409


async def test_you_cannot_submit_someone_elses_food(client: TestClient) -> None:
    use_reviewer(PLAUSIBLE)
    mine = account(client, "owner2@example.com")
    food_id = add_food(client, mine)

    theirs = account(client, "thief@example.com")
    assert client.post(f"/api/v1/review/foods/{food_id}/submit", headers=theirs).status_code == 404


# --------------------------------------------------------------------------- #
# The admin gate
# --------------------------------------------------------------------------- #


async def test_the_queue_is_invisible_to_ordinary_users(client: TestClient) -> None:
    """404 rather than 403. A 403 confirms the endpoint exists and maps the
    admin surface for anyone probing."""
    ordinary = account(client, "nosy@example.com")

    assert client.get("/api/v1/review/queue", headers=ordinary).status_code == 404


async def test_an_admin_sees_the_queue(client: TestClient, session) -> None:
    use_reviewer(PLAUSIBLE)
    mine = account(client, "contrib@example.com")
    food_id = add_food(client, mine)
    client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)

    boss = await admin_account(client, session, "boss@example.com")

    queue = client.get("/api/v1/review/queue", headers=boss)
    assert queue.status_code == 200, queue.text
    assert [item["food"]["id"] for item in queue.json()] == [food_id]


async def test_the_queue_can_be_filtered_by_the_models_verdict(client: TestClient, session) -> None:
    """The point of screening: take the `not_food` pile in one pass rather than
    reading everything at the same depth."""
    use_reviewer(ReviewOpinion(verdict="not_food", reason="This is not a food."))
    mine = account(client, "spam@example.com")
    spam_id = add_food(client, mine, "Zzqx Nonsense")
    client.post(f"/api/v1/review/foods/{spam_id}/submit", headers=mine)

    boss = await admin_account(client, session, "admin2@example.com")

    flagged = client.get("/api/v1/review/queue?verdict=not_food", headers=boss).json()
    assert [item["food"]["id"] for item in flagged] == [spam_id]

    clean = client.get("/api/v1/review/queue?verdict=plausible", headers=boss).json()
    assert clean == []


# --------------------------------------------------------------------------- #
# The decision
# --------------------------------------------------------------------------- #


async def test_approval_is_what_makes_a_food_public(client: TestClient, session) -> None:
    """The property this whole module exists to guarantee."""
    use_reviewer(PLAUSIBLE)
    mine = account(client, "sharer@example.com")
    food_id = add_food(client, mine)
    client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)

    boss = await admin_account(client, session, "admin3@example.com")

    stranger = account(client, "public@example.com")
    assert client.get("/api/v1/foods/search?q=Zzqx", headers=stranger).json()["results"] == []

    decided = client.post(
        f"/api/v1/review/foods/{food_id}/decide", headers=boss, json={"approve": True}
    )
    assert decided.status_code == 200, decided.text

    now_visible = client.get("/api/v1/foods/search?q=Zzqx", headers=stranger).json()
    assert [r["id"] for r in now_visible["results"]] == [food_id]


async def test_an_admin_can_correct_a_submission_while_approving(
    client: TestClient, session
) -> None:
    """A reviewer fixing a typo should not have to restate the nutrition, so
    every correction field is optional and absent means "leave as submitted"."""
    use_reviewer(PLAUSIBLE)
    mine = account(client, "typo@example.com")
    food_id = add_food(client, mine, "Zzqx Bqr")
    client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)

    boss = await admin_account(client, session, "admin4@example.com")

    body = client.post(
        f"/api/v1/review/foods/{food_id}/decide",
        headers=boss,
        json={"approve": True, "name": "Zzqx Bar", "kcal": 380},
    ).json()

    assert body["food"]["name"] == "Zzqx Bar"
    assert body["food"]["kcal"] == 380
    # Untouched fields keep what the author submitted.
    assert body["food"]["protein_g"] == 10


async def test_a_rejection_needs_a_reason(client: TestClient, session) -> None:
    """A refusal without a reason is the kind of thing that makes people stop
    contributing."""
    use_reviewer(PLAUSIBLE)
    mine = account(client, "rejected@example.com")
    food_id = add_food(client, mine)
    client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)

    boss = await admin_account(client, session, "admin5@example.com")

    bare = client.post(
        f"/api/v1/review/foods/{food_id}/decide", headers=boss, json={"approve": False}
    )
    assert bare.status_code == 422


async def test_a_rejected_food_stays_usable_by_its_author(client: TestClient, session) -> None:
    """Not deleted. Their diary references it, and leaving their history
    readable is worth more than reclaiming a row."""
    use_reviewer(PLAUSIBLE)
    mine = account(client, "keeper@example.com")
    food_id = add_food(client, mine)
    client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)

    boss = await admin_account(client, session, "admin6@example.com")

    client.post(
        f"/api/v1/review/foods/{food_id}/decide",
        headers=boss,
        json={"approve": False, "note": "Not a real product."},
    )

    own = client.get("/api/v1/foods/search?q=Zzqx", headers=mine).json()
    assert [r["id"] for r in own["results"]] == [food_id]

    stranger = account(client, "nope@example.com")
    assert client.get("/api/v1/foods/search?q=Zzqx", headers=stranger).json()["results"] == []


async def test_the_author_can_read_why_it_was_rejected(client: TestClient, session) -> None:
    use_reviewer(PLAUSIBLE)
    mine = account(client, "curious@example.com")
    food_id = add_food(client, mine)
    client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)

    boss = await admin_account(client, session, "admin7@example.com")

    client.post(
        f"/api/v1/review/foods/{food_id}/decide",
        headers=boss,
        json={"approve": False, "note": "Numbers do not match the named product."},
    )

    mine_list = client.get("/api/v1/review/foods/mine", headers=mine).json()
    assert mine_list[0]["review_status"] == "rejected"
    assert "Numbers do not match" in mine_list[0]["review_note"]


async def test_a_decision_cannot_be_made_twice(client: TestClient, session) -> None:
    use_reviewer(PLAUSIBLE)
    mine = account(client, "once@example.com")
    food_id = add_food(client, mine)
    client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)

    boss = await admin_account(client, session, "admin8@example.com")

    client.post(f"/api/v1/review/foods/{food_id}/decide", headers=boss, json={"approve": True})
    again = client.post(
        f"/api/v1/review/foods/{food_id}/decide", headers=boss, json={"approve": True}
    )
    assert again.status_code == 409


async def test_the_model_verdict_never_decides_by_itself(client: TestClient, session) -> None:
    """Even a `not_food` verdict leaves the submission pending. The model sorts
    the queue; a person empties it."""
    use_reviewer(ReviewOpinion(verdict="not_food", reason="Gibberish."))
    mine = account(client, "judge@example.com")
    food_id = add_food(client, mine)

    body = client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine).json()

    assert body["llm_verdict"] == "not_food"
    assert body["review_status"] == "pending"
    assert body["reviewed_at"] is None

    stored = (
        await session.execute(select(User).where(User.email == "judge@example.com"))
    ).scalar_one()
    assert stored is not None


async def test_the_review_queue_view_shows_what_a_reviewer_needs(
    client: TestClient, session
) -> None:
    """The view Supabase Studio is pointed at.

    Tested because it is the actual admin interface — an untested view is an
    admin tool that breaks silently the next time a column is renamed.
    """
    from sqlalchemy import text as sql

    use_reviewer(ReviewOpinion(verdict="suspect", reason="Fat looks high for a cereal bar."))
    mine = account(client, "viewer@example.com")
    food_id = add_food(client, mine, "Zzqx Viewtest")
    client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)

    row = (
        await session.execute(
            sql("SELECT * FROM review_queue WHERE name = 'Zzqx Viewtest'")
        )
    ).mappings().one()

    assert row["verdict"] == "suspect"
    assert "Fat looks high" in row["verdict_reason"]
    assert row["submitted_by"] == "viewer@example.com"
    # 4*10 + 4*50 + 9*15 = 375, against the 400 declared. Close enough to pass
    # the importer, far enough apart to be worth a reviewer's eye.
    assert row["kcal_implied_by_macros"] == 375
    # First-time contributor.
    assert row["author_approved_count"] == 0


async def test_a_decided_submission_leaves_the_queue_view(
    client: TestClient, session
) -> None:
    from sqlalchemy import text as sql

    use_reviewer(PLAUSIBLE)
    mine = account(client, "leaves@example.com")
    food_id = add_food(client, mine, "Zzqx Leaves")
    client.post(f"/api/v1/review/foods/{food_id}/submit", headers=mine)

    boss = await admin_account(client, session, "admin9@example.com")
    client.post(f"/api/v1/review/foods/{food_id}/decide", headers=boss, json={"approve": True})

    remaining = (
        await session.execute(
            sql("SELECT count(*) FROM review_queue WHERE name = 'Zzqx Leaves'")
        )
    ).scalar_one()
    assert remaining == 0
