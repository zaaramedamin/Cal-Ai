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
