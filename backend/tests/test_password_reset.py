"""Password reset flow.

The security-relevant assertions are that the endpoint cannot be used to
discover which addresses have accounts, that a token works exactly once, and
that completing a reset kicks every existing session out.
"""

from fastapi.testclient import TestClient

EMAIL = "reset-me@example.com"
PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "an-entirely-different-one"


def register(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password})


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def request_reset(client: TestClient, email: str = EMAIL):
    return client.post("/api/v1/auth/password-reset/request", json={"email": email})


def confirm_reset(client: TestClient, token: str, new_password: str = NEW_PASSWORD):
    return client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": new_password},
    )


def issue_token(client: TestClient) -> str:
    """Request a reset and return the token, using the development-only echo."""
    body = request_reset(client).json()
    assert body["debug_reset_token"], "development echo should be populated"
    return body["debug_reset_token"]


# --------------------------------------------------------------------------- #
# Requesting
# --------------------------------------------------------------------------- #


def test_request_is_accepted_for_a_real_account(client: TestClient) -> None:
    register(client)
    assert request_reset(client).status_code == 202


def test_request_does_not_reveal_whether_the_account_exists(client: TestClient) -> None:
    """The whole point of the neutral response.

    A different status or message for an unknown address would turn this into a
    free tool for discovering who has an account — and unlike registration, there
    is no usability cost to staying quiet.
    """
    register(client)
    known = request_reset(client)
    unknown = request_reset(client, email="nobody-at-all@example.com")

    assert known.status_code == unknown.status_code == 202
    assert known.json()["message"] == unknown.json()["message"]


def test_no_token_is_issued_for_an_unknown_account(client: TestClient) -> None:
    assert request_reset(client, email="nobody-at-all@example.com").json()[
        "debug_reset_token"
    ] is None


def test_requesting_again_invalidates_the_previous_link(client: TestClient) -> None:
    """Otherwise every request leaves another live key in the user's inbox."""
    register(client)
    first = issue_token(client)
    second = issue_token(client)

    assert first != second
    assert confirm_reset(client, first).status_code == 400
    assert confirm_reset(client, second).status_code == 204


# --------------------------------------------------------------------------- #
# Confirming
# --------------------------------------------------------------------------- #


def test_reset_changes_the_password(client: TestClient) -> None:
    register(client)
    assert confirm_reset(client, issue_token(client)).status_code == 204

    assert login(client, password=PASSWORD).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_token_works_only_once(client: TestClient) -> None:
    register(client)
    token = issue_token(client)

    assert confirm_reset(client, token).status_code == 204
    assert confirm_reset(client, token, "yet-another-password").status_code == 400


def test_unknown_token_is_rejected(client: TestClient) -> None:
    assert confirm_reset(client, "a-token-that-never-existed").status_code == 400


def test_short_new_password_is_rejected(client: TestClient) -> None:
    register(client)
    assert confirm_reset(client, issue_token(client), "short").status_code == 422


def test_reset_revokes_every_existing_session(client: TestClient) -> None:
    """The assertion that makes this a recovery mechanism rather than a convenience.

    Someone resetting their password often believes they were compromised. An
    attacker holds a refresh token, not the password — so changing the password
    alone would not touch them. Only revoking the sessions does.
    """
    register(client)
    phone = login(client).json()["refresh_token"]
    laptop = login(client).json()["refresh_token"]

    assert confirm_reset(client, issue_token(client)).status_code == 204

    for token in (phone, laptop):
        assert (
            client.post("/api/v1/auth/refresh", json={"refresh_token": token}).status_code == 401
        )


def test_access_token_is_rejected_after_reset_once_refreshed(client: TestClient) -> None:
    """Honest about the limit of stateless access tokens.

    The old *access* token keeps working until it expires — verifying it involves
    no database lookup, which is the whole point of a JWT. What the reset
    guarantees is that it cannot be renewed. This test documents that boundary so
    nobody later assumes reset is instant everywhere.
    """
    register(client)
    session = login(client).json()

    confirm_reset(client, issue_token(client))

    # Still valid: it has not expired yet.
    assert (
        client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {session['access_token']}"}
        ).status_code
        == 200
    )
    # But it can never be renewed.
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}
        ).status_code
        == 401
    )
