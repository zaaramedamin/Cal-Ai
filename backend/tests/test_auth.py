"""Authentication flows.

The interesting tests here are the negative ones. Any implementation makes
"register then log in" work; the ones that matter are whether a revoked token
stays revoked, whether reuse is detected, and whether a wrong password is
distinguishable from a missing account.
"""

from fastapi.testclient import TestClient

EMAIL = "zaara@example.com"
PASSWORD = "correct-horse-battery"


def register(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password})


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def test_register_returns_tokens_and_user(client: TestClient) -> None:
    response = register(client)
    assert response.status_code == 201

    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0
    assert body["user"]["email"] == EMAIL


def test_register_never_returns_credential_material(client: TestClient) -> None:
    """The response must not leak the hash or the password.

    Guards against someone later "simplifying" UserRead into returning the ORM
    object, which would ship password_hash to every client. Checking the raw
    response body catches it wherever in the payload it might appear.
    """
    response = register(client)
    assert "password_hash" not in response.json()["user"]
    assert "password_hash" not in response.text
    assert PASSWORD not in response.text


def test_duplicate_email_is_rejected(client: TestClient) -> None:
    assert register(client).status_code == 201
    assert register(client).status_code == 409


def test_email_uniqueness_is_case_insensitive(client: TestClient) -> None:
    """CITEXT doing its job.

    Without it, Zaara@Example.com and zaara@example.com become two accounts, and
    the user cannot understand why their password 'stopped working'.
    """
    assert register(client, email="zaara@example.com").status_code == 201
    assert register(client, email="ZAARA@Example.COM").status_code == 409


def test_can_log_in_with_differently_cased_email(client: TestClient) -> None:
    register(client, email="zaara@example.com")
    assert login(client, email="ZaArA@ExAmPlE.cOm").status_code == 200


def test_short_password_is_rejected(client: TestClient) -> None:
    response = register(client, password="short")
    assert response.status_code == 422


def test_malformed_email_is_rejected(client: TestClient) -> None:
    assert register(client, email="not-an-email").status_code == 422


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #


def test_login_with_wrong_password_fails(client: TestClient) -> None:
    register(client)
    assert login(client, password="wrong-password-entirely").status_code == 401


def test_login_for_unknown_account_fails(client: TestClient) -> None:
    assert login(client, email="nobody@example.com").status_code == 401


def test_login_does_not_reveal_whether_the_account_exists(client: TestClient) -> None:
    """Both failures must be indistinguishable to the caller.

    If a missing account returned a different status or message from a wrong
    password, anyone could enumerate which email addresses are registered.
    """
    register(client)
    wrong_password = login(client, password="wrong-password-entirely")
    unknown_account = login(client, email="nobody@example.com")

    assert wrong_password.status_code == unknown_account.status_code == 401
    assert wrong_password.json() == unknown_account.json()


def test_each_login_issues_a_distinct_refresh_token(client: TestClient) -> None:
    """Two devices must get two independent sessions.

    If logins shared a token, signing out on one device would sign out the other.
    """
    register(client)
    first = login(client).json()["refresh_token"]
    second = login(client).json()["refresh_token"]
    assert first != second


# --------------------------------------------------------------------------- #
# Protected routes
# --------------------------------------------------------------------------- #


def test_me_requires_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/users/me").status_code == 401


def test_me_rejects_a_garbage_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


def test_me_rejects_a_token_signed_with_the_wrong_key(client: TestClient) -> None:
    """A forged token must not be accepted.

    This is the test that would fail if someone ever passed
    `options={"verify_signature": False}` while debugging and forgot to remove it.
    """
    import jwt

    forged = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000001", "exp": 9999999999, "type": "access"},
        "not-the-real-secret-key-not-even-close",
        algorithm="HS256",
    )
    response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_me_returns_the_signed_in_user(client: TestClient) -> None:
    tokens = register(client).json()
    response = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


def test_refresh_token_is_not_accepted_as_an_access_token(client: TestClient) -> None:
    """Token confusion guard.

    A refresh token is opaque and carries no signature we would accept here, but
    asserting it explicitly is what stops a future change — say, making refresh
    tokens JWTs for convenience — from silently making them interchangeable.
    """
    tokens = register(client).json()
    response = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Refresh, rotation and theft detection
# --------------------------------------------------------------------------- #


def refresh(client: TestClient, token: str):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": token})


def test_refresh_returns_a_new_pair(client: TestClient) -> None:
    original = register(client).json()
    response = refresh(client, original["refresh_token"])

    assert response.status_code == 200
    rotated = response.json()
    assert rotated["refresh_token"] != original["refresh_token"]
    assert rotated["access_token"]


def test_rotated_token_grants_access(client: TestClient) -> None:
    original = register(client).json()
    rotated = refresh(client, original["refresh_token"]).json()

    response = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {rotated['access_token']}"}
    )
    assert response.status_code == 200


def test_old_refresh_token_stops_working_after_rotation(client: TestClient) -> None:
    """The point of rotation: a token is spent once."""
    original = register(client).json()["refresh_token"]
    refresh(client, original)
    assert refresh(client, original).status_code == 401


def test_reusing_a_spent_token_revokes_every_session(client: TestClient) -> None:
    """Theft detection.

    A spent token being presented again means two parties hold it — the real
    client and a thief — and we cannot tell them apart. Revoking everything and
    forcing a fresh login is the only safe response. Being logged out
    unexpectedly beats an attacker keeping a session indefinitely.
    """
    original = register(client).json()["refresh_token"]
    rotated = refresh(client, original).json()["refresh_token"]

    # The thief replays the spent token.
    assert refresh(client, original).status_code == 401

    # The legitimate client's current token is now dead too.
    assert refresh(client, rotated).status_code == 401


def test_refresh_rejects_an_unknown_token(client: TestClient) -> None:
    assert refresh(client, "completely-made-up-token").status_code == 401


# --------------------------------------------------------------------------- #
# Logout
# --------------------------------------------------------------------------- #


def test_logout_revokes_the_refresh_token(client: TestClient) -> None:
    token = register(client).json()["refresh_token"]

    assert client.post("/api/v1/auth/logout", json={"refresh_token": token}).status_code == 204
    assert refresh(client, token).status_code == 401


def test_logout_is_silent_about_unknown_tokens(client: TestClient) -> None:
    """204 regardless, so the endpoint cannot be used to test whether a token is valid."""
    response = client.post("/api/v1/auth/logout", json={"refresh_token": "never-existed"})
    assert response.status_code == 204


def test_logout_only_affects_the_device_that_logged_out(client: TestClient) -> None:
    register(client)
    phone = login(client).json()["refresh_token"]
    laptop = login(client).json()["refresh_token"]

    client.post("/api/v1/auth/logout", json={"refresh_token": phone})

    assert refresh(client, phone).status_code == 401
    assert refresh(client, laptop).status_code == 200


def test_replaying_a_logged_out_token_does_not_sign_out_other_devices(
    client: TestClient,
) -> None:
    """A logged-out token is not evidence of theft.

    A stale client retrying with a token it does not yet know was revoked is the
    common case. If that triggered the theft response, signing out on one device
    would cascade into signing the user out everywhere — an infuriating bug that
    would look completely random from the outside.

    Only a *rotated* token being replayed means two copies exist. That is the
    case theft detection is for, and it is asserted separately above.
    """
    register(client)
    phone = login(client).json()["refresh_token"]
    laptop = login(client).json()["refresh_token"]

    client.post("/api/v1/auth/logout", json={"refresh_token": phone})

    # The signed-out phone retries several times, as a real app would.
    for _ in range(3):
        assert refresh(client, phone).status_code == 401

    # The laptop is untouched throughout.
    assert refresh(client, laptop).status_code == 200


def test_logout_all_revokes_every_session(client: TestClient) -> None:
    tokens = register(client).json()
    laptop = login(client).json()["refresh_token"]

    response = client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 204

    assert refresh(client, tokens["refresh_token"]).status_code == 401
    assert refresh(client, laptop).status_code == 401


def test_logout_all_requires_authentication(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout-all").status_code == 401
