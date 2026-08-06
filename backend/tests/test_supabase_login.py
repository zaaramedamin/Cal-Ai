"""Signing in with a Supabase token, end to end through a real endpoint.

`test_supabase_auth.py` covers whether a token verifies. This covers what happens
next: that a verified token resolves to a row in `users`, that the row is created
on first sight, and that the legacy tokens keep working alongside it — which is
the whole reason the mobile app can be migrated a screen at a time.
"""

import time
import uuid
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from app.core.config import get_settings
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


def register_local(client, email: str = "local@example.com") -> dict:
    """Create an account through the hand-built auth, as the app does today."""
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"email": email, "id": body["user"]["id"], "token": body["access_token"]}


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


async def test_a_supabase_login_cannot_take_over_an_existing_email(
    client, signing_key, session
):
    """The dangerous case.

    If someone signs in through Supabase with an address that already belongs to
    a local account, the ids differ and the email is unique — so provisioning
    fails. It must refuse rather than silently attach the login to that person's
    diary.
    """
    existing = register_local(client, "taken@example.com")
    token = supabase_token(signing_key, uuid.uuid4(), existing["email"])

    response = client.get("/api/v1/users/me", headers=auth(token))
    assert response.status_code == 401


async def test_legacy_tokens_still_work(client):
    """What makes the migration incremental: the app keeps working on the old
    tokens until its screens have moved over."""
    existing = register_local(client, "legacy@example.com")

    response = client.get("/api/v1/users/me", headers=auth(existing["token"]))
    assert response.status_code == 200
    assert response.json()["email"] == "legacy@example.com"


async def test_a_forged_supabase_token_does_not_fall_through_to_the_legacy_path(
    client, signing_key
):
    """The fallback must not become a bypass.

    A token that fails Supabase verification is tried against the legacy scheme,
    and that is fine only because the legacy check verifies its own signature. A
    forged ES256 token is not a valid HS256 one, so it is refused twice rather
    than once.
    """
    other_key = ec.generate_private_key(ec.SECP256R1())
    forged = supabase_token(other_key, uuid.uuid4(), "attacker@example.com")

    assert client.get("/api/v1/users/me", headers=auth(forged)).status_code == 401


async def test_no_token_is_still_401(client):
    assert client.get("/api/v1/users/me").status_code == 401
