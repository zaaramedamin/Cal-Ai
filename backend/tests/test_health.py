"""Health endpoint contract.

Deliberately written to pass whether or not Postgres is running, because the
endpoint's whole purpose is to report either situation honestly. A test that
required a live database would be testing the database; these test the contract.
"""

from fastapi.testclient import TestClient

from app import __version__
from app.main import app


def test_health_always_answers_200() -> None:
    """Even a dead database must not turn into a 500.

    The mobile app distinguishes "no response at all" from "responded, database
    down". If this endpoint threw on a database failure, both would arrive at the
    client as an unreachable server and the distinction would be lost.
    """
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_shape_and_invariant() -> None:
    with TestClient(app) as client:
        body = client.get("/api/v1/health").json()

    assert set(body) == {"status", "version", "db"}
    assert body["version"] == __version__
    assert body["db"] in {"ok", "unreachable"}
    assert body["status"] in {"ok", "degraded"}

    # The invariant that gives the field meaning: overall status is healthy
    # exactly when the database is reachable. Without this, `status` could drift
    # into always reporting "ok" and nothing would catch it.
    assert (body["status"] == "ok") == (body["db"] == "ok")


def test_health_is_published_in_the_openapi_schema() -> None:
    """The mobile client is generated from this schema, so its presence is part
    of the contract, not an implementation detail."""
    assert "/api/v1/health" in app.openapi()["paths"]


async def test_a_dead_database_says_so_in_json(client, monkeypatch) -> None:
    """The failure that produced "something went wrong on the server".

    Stopping Postgres while the API keeps running is a normal accident on this
    project — the database is a container you start separately. Unhandled, that
    raises inside the request, Starlette answers with a **plain-text** 500, the
    mobile client cannot parse a `detail` out of plain text, and it falls back to
    its most generic message. The one machine that knows exactly what is wrong
    ends up saying the least about it.

    Two things are asserted, and the second matters as much as the first: the
    status is a 503 (the service is unavailable, the request was not invalid),
    and the body is JSON carrying a `detail` the app can display verbatim.
    """
    # The *real* exception, recorded from a live run with the container stopped:
    # asyncpg raises a bare ConnectionRefusedError because the connect fails
    # before SQLAlchemy has a statement to wrap. The first version of this test
    # raised OperationalError instead — an assumption about the type — and passed
    # against a handler that caught nothing in production.
    async def refuse(*args, **kwargs):
        raise ConnectionRefusedError(1225, "The remote computer refused the network connection")

    # Patched on the session the endpoint actually uses, so this exercises the
    # real exception path rather than a hand-raised error in a handler.
    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", refuse)

    # Login, because it reaches the database through `execute` — the path the
    # patch above intercepts. Register writes via flush/commit instead, so it
    # would sail past this patch and prove nothing.
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "dbdown@example.com", "password": "correct-horse-battery"},
    )

    assert response.status_code == 503
    body = response.json()
    assert "docker compose up -d" in body["detail"]


async def test_a_dying_pooled_connection_also_says_so(client, monkeypatch) -> None:
    """The other half of "database unreachable".

    A connection that dies while checked out — or a pre-ping failing on a stale
    socket — surfaces as SQLAlchemy's DBAPIError rather than a raw OS error. Both
    mean the same thing to the user, so both must produce the same answer.
    """
    from sqlalchemy.exc import OperationalError

    async def refuse(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, ConnectionRefusedError(1225, "refused"))

    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", refuse)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "dbdown2@example.com", "password": "correct-horse-battery"},
    )

    assert response.status_code == 503
    assert "docker compose up -d" in response.json()["detail"]
