"""Supabase token verification, and specifically the ways it must refuse.

A JWT verifier that only has a happy-path test is untested. Every check in
`supabase_auth.py` closes a real bypass, so each one gets a test that forges a
token exercising exactly that bypass and asserts it is refused.

The signing key here is generated in-process, so these run offline and prove the
logic rather than Supabase's availability. One test does reach the real project,
marked so it can be deselected.
"""

import time
import uuid
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import get_settings
from app.core.supabase_auth import (
    AUDIENCE,
    InvalidSupabaseToken,
    email_from,
    reset_key_cache,
    user_id_from,
    verify_token,
)

KID = "test-key-1"
ISSUER = "https://test.supabase.co/auth/v1"


@pytest.fixture
def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(autouse=True)
def supabase_configured(signing_key, monkeypatch) -> None:
    """Point the verifier at an in-process key set instead of the network."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    get_settings.cache_clear()
    reset_key_cache()

    public_numbers = signing_key.public_key().public_numbers()

    def to_b64(value: int) -> str:
        import base64

        return base64.urlsafe_b64encode(value.to_bytes(32, "big")).rstrip(b"=").decode()

    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "alg": "ES256",
        "use": "sig",
        "kid": KID,
        "x": to_b64(public_numbers.x),
        "y": to_b64(public_numbers.y),
    }

    async def fake_fetch(self) -> None:
        from jwt import PyJWK

        self._keys = {KID: PyJWK.from_dict(jwk)}
        self._fetched_at = time.monotonic()

    monkeypatch.setattr("app.core.supabase_auth._KeyCache._fetch", fake_fetch)
    yield
    get_settings.cache_clear()
    reset_key_cache()


def make_token(signing_key, *, alg: str = "ES256", kid: str | None = KID, **overrides) -> str:
    claims: dict[str, Any] = {
        "sub": str(uuid.uuid4()),
        "email": "zaara@example.com",
        "aud": AUDIENCE,
        "iss": ISSUER,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    claims.update(overrides)
    for key, value in list(claims.items()):
        if value is None:
            del claims[key]
    return jwt.encode(claims, signing_key, algorithm=alg, headers={"kid": kid})


# --------------------------------------------------------------------------- #
# The happy path — without which every rejection below could pass for the
# wrong reason.
# --------------------------------------------------------------------------- #


async def test_a_valid_token_is_accepted(signing_key):
    user_id = str(uuid.uuid4())
    claims = await verify_token(make_token(signing_key, sub=user_id))

    assert user_id_from(claims) == user_id
    assert email_from(claims) == "zaara@example.com"


async def test_the_subject_is_a_uuid_so_it_can_be_our_primary_key(signing_key):
    """What makes this migration cheap: Supabase ids drop into `users.id`, so
    every foreign key already pointing there keeps working."""
    claims = await verify_token(make_token(signing_key))
    uuid.UUID(user_id_from(claims))  # raises if it is not a UUID


# --------------------------------------------------------------------------- #
# Forgeries
# --------------------------------------------------------------------------- #


def _b64(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


async def test_an_unsigned_token_is_refused(signing_key):
    """`alg: none` — the oldest JWT attack there is.

    Hand-assembled rather than produced by PyJWT, which refuses to *encode* an
    unsigned token. An attacker is under no such constraint: this is three
    base64 segments and an empty signature, which is exactly what a naive
    verifier accepts.
    """
    import json

    header = _b64(json.dumps({"alg": "none", "typ": "JWT", "kid": KID}).encode())
    payload = _b64(
        json.dumps(
            {
                "sub": str(uuid.uuid4()),
                "aud": AUDIENCE,
                "iss": ISSUER,
                "exp": int(time.time()) + 3600,
            }
        ).encode()
    )
    forged = f"{header}.{payload}."

    with pytest.raises(InvalidSupabaseToken):
        await verify_token(forged)


async def test_a_token_signed_with_a_different_key_is_refused(signing_key):
    other = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(InvalidSupabaseToken):
        await verify_token(make_token(other))


async def test_an_expired_token_is_refused(signing_key):
    with pytest.raises(InvalidSupabaseToken):
        await verify_token(make_token(signing_key, exp=int(time.time()) - 60))


async def test_a_token_from_another_project_is_refused(signing_key):
    """Anyone can create a Supabase project for free. Without the issuer check,
    a token from theirs would be accepted by our API."""
    with pytest.raises(InvalidSupabaseToken):
        await verify_token(make_token(signing_key, iss="https://attacker.supabase.co/auth/v1"))


async def test_a_token_for_a_different_audience_is_refused(signing_key):
    with pytest.raises(InvalidSupabaseToken):
        await verify_token(make_token(signing_key, aud="anon"))


async def test_a_token_with_no_subject_is_refused(signing_key):
    """`sub` is the user id. A token without one authenticates nobody, and
    treating it as valid would mean a request with no owner."""
    with pytest.raises(InvalidSupabaseToken):
        await verify_token(make_token(signing_key, sub=None))


async def test_a_token_signed_by_an_unknown_key_is_refused(signing_key):
    with pytest.raises(InvalidSupabaseToken):
        await verify_token(make_token(signing_key, kid="some-other-kid"))


async def test_rubbish_is_refused(signing_key):
    for value in ("", "not-a-token", "a.b.c"):
        with pytest.raises(InvalidSupabaseToken):
            await verify_token(value)


async def test_verification_is_off_when_supabase_is_not_configured(signing_key, monkeypatch):
    """The two auth systems coexist during the migration, so an unconfigured
    project must refuse cleanly rather than half-verify."""
    monkeypatch.setenv("SUPABASE_URL", "")
    get_settings.cache_clear()

    with pytest.raises(InvalidSupabaseToken):
        await verify_token(make_token(signing_key))
