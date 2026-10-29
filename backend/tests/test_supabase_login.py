"""Signing in with a Supabase token, end to end through a real endpoint.

`test_supabase_auth.py` covers whether a token verifies. This covers what happens
next: that a verified token resolves to a row in `users`, that the row is created
on first sight, and that the hand-built auth is shut — its routes and its tokens
both — for as long as Supabase is configured.
"""

import time
import uuid
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.core.supabase_auth import AUDIENCE, reset_key_cache
from app.db.models.user import User

KID = "test-key-1"
PROJECT = "https://test.supabase.co"
ISSUER = f"{PROJECT}/auth/v1"


@pytest.fixture
def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(autouse=True)
def supabase_configured(signing_key, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", PROJECT)
    get_settings.cache_clear()
    reset_key_cache()

    numbers = signing_key.public_key().public_numbers()

    def b64(value: int) -> str:
        import base64

        return base64.urlsafe_b64encode(value.to_bytes(32, "big")).rstrip(b"=").decode()

    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "alg": "ES256",
        "use": "sig",
        "kid": KID,
        "x": b64(numbers.x),
        "y": b64(numbers.y),
    }

    async def fake_fetch(self) -> None:
        from jwt import PyJWK

        self._keys = {KID: PyJWK.from_dict(jwk)}
        self._fetched_at = time.monotonic()

    monkeypatch.setattr("app.core.supabase_auth._KeyCache._fetch", fake_fetch)
    yield
    get_settings.cache_clear()
    reset_key_cache()


def supabase_token(signing_key, user_id: uuid.UUID, email: str) -> str:
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "aud": AUDIENCE,
        "iss": ISSUER,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    return jwt.encode(claims, signing_key, algorithm="ES256", headers={"kid": KID})


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def local_account(session, email: str = "local@example.com") -> User:
    """A hand-built account, written straight to the table.

    Not through `/auth/register`: that route is shut while Supabase is on, which
    is what these tests are about. The row stands in for one created before the
    switch, or by the lockout this change closes.
    """
    user = User(email=email, password_hash=hash_password("correct-horse-battery"))
    session.add(user)
    await session.commit()
    return user


# --------------------------------------------------------------------------- #


async def test_first_request_creates_the_local_account(client, signing_key, session):
    """Supabase owns the credential; this table owns the profile and the diary's
    foreign keys. The row has to appear at some point, and the first
    authenticated request is the earliest we know the account is real."""
    user_id = uuid.uuid4()
    token = supabase_token(signing_key, user_id, "new@example.com")

    response = client.get("/api/v1/users/me", headers=auth(token))
    assert response.status_code == 200, response.text
    assert response.json()["email"] == "new@example.com"

    row = await session.get(User, user_id)
    assert row is not None
    assert row.password_hash is None, "a Supabase account must hold no local password"
    assert row.is_supabase_account


async def test_provisioning_happens_once(client, signing_key, session):
    """Repeated requests must not pile up rows or 500 on the unique constraint."""
    user_id = uuid.uuid4()
    token = supabase_token(signing_key, user_id, "repeat@example.com")

    for _ in range(3):
        assert client.get("/api/v1/users/me", headers=auth(token)).status_code == 200

    rows = (await session.execute(select(User).where(User.id == user_id))).scalars().all()
    assert len(rows) == 1


async def test_a_returning_user_costs_no_write(client, signing_key, engine):
    """Every request but the first finds the row, so none but the first writes.

    Provisioning used to INSERT and COMMIT on every request regardless — three
    round trips to eu-north-1 before the endpoint did any work of its own.
    """
    from sqlalchemy import event

    token = supabase_token(signing_key, uuid.uuid4(), "returning@example.com")
    assert client.get("/api/v1/users/me", headers=auth(token)).status_code == 200

    statements: list[str] = []

    def record(_conn, _cursor, statement, *_args) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        assert client.get("/api/v1/users/me", headers=auth(token)).status_code == 200
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)

    assert statements, "the listener saw nothing, so this test proves nothing"
    assert not [s for s in statements if s.lstrip().upper().startswith("INSERT")]


async def test_a_supabase_login_cannot_take_over_an_existing_email(
    client, signing_key, session
):
    """The dangerous case.

    If someone signs in through Supabase with an address that already belongs to
    a local account, the ids differ and the email is unique — so provisioning
    fails. It must refuse rather than silently attach the login to that person's
    diary.
    """
    existing = await local_account(session, "taken@example.com")
    token = supabase_token(signing_key, uuid.uuid4(), existing.email)

    response = client.get("/api/v1/users/me", headers=auth(token))
    assert response.status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/logout-all",
        "/api/v1/auth/password-reset/request",
        "/api/v1/auth/password-reset/confirm",
    ],
)
async def test_the_hand_built_routes_are_shut(client, path):
    """Every one of them, not just `/register`.

    `/register` is the one that did damage: an unconfirmed account on somebody
    else's address made their later Supabase sign-up fail for good, by the rule
    the test above protects. But `/login` and `/refresh` would keep issuing
    tokens the server no longer accepts, and the reset routes would email links
    for passwords nobody signs in with.
    """
    response = client.post(path, json={"email": "victim@example.com", "password": "x" * 12})
    assert response.status_code == 404, response.text


async def test_registering_creates_no_row(client, signing_key, session):
    """The lockout, end to end: the route is shut, so the address stays free and
    its owner's Supabase sign-up goes through."""
    client.post(
        "/api/v1/auth/register",
        json={"email": "victim@example.com", "password": "correct-horse-battery"},
    )

    token = supabase_token(signing_key, uuid.uuid4(), "victim@example.com")
    response = client.get("/api/v1/users/me", headers=auth(token))
    assert response.status_code == 200, response.text


async def test_a_hand_built_token_is_refused(client, session):
    """Validly signed with `SECRET_KEY`, for a real account — and still refused.

    Accepting these alongside Supabase's meant anyone holding `SECRET_KEY` could
    sign in as anybody, on a server whose sign-in no longer uses that key.
    """
    existing = await local_account(session, "legacy@example.com")
    token, _ = create_access_token(existing.id)

    assert client.get("/api/v1/users/me", headers=auth(token)).status_code == 401


async def test_a_forged_supabase_token_is_refused(client, signing_key):
    """Signed by a key that is not the project's, so verification must fail —
    and with no second scheme behind it to fall through to."""
    other_key = ec.generate_private_key(ec.SECP256R1())
    forged = supabase_token(other_key, uuid.uuid4(), "attacker@example.com")

    assert client.get("/api/v1/users/me", headers=auth(forged)).status_code == 401


async def test_no_token_is_still_401(client):
    assert client.get("/api/v1/users/me").status_code == 401
