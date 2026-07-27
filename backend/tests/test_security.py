"""Password hashing and token primitives.

Pure unit tests — no database, no HTTP. These pin the properties the rest of the
auth system assumes are true.
"""

import uuid

import jwt

from app.core.config import get_settings
from app.core.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

PASSWORD = "correct-horse-battery"


def test_hash_does_not_contain_the_password() -> None:
    assert PASSWORD not in hash_password(PASSWORD)


def test_hash_is_argon2id() -> None:
    """The variant matters: argon2i and argon2d each drop one of the protections."""
    assert hash_password(PASSWORD).startswith("$argon2id$")


def test_same_password_hashes_differently_every_time() -> None:
    """Proves a random salt is in use.

    Without per-password salts, identical passwords produce identical hashes, and
    one precomputed rainbow table cracks every account that shares a password.
    """
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verify_accepts_the_right_password() -> None:
    assert verify_password(PASSWORD, hash_password(PASSWORD))


def test_verify_rejects_the_wrong_password() -> None:
    assert not verify_password("something-else-entirely", hash_password(PASSWORD))


def test_verify_returns_false_on_a_malformed_hash() -> None:
    """A corrupt row is a failed login, not a 500."""
    assert not verify_password(PASSWORD, "not-a-valid-argon2-hash")


def test_access_token_round_trips() -> None:
    user_id = uuid.uuid4()
    token, _ = create_access_token(user_id)
    assert decode_access_token(token) == user_id


def test_access_token_carries_no_secrets() -> None:
    """A JWT is signed, not encrypted — anyone holding it can read the payload.

    So the payload must contain nothing private. Decoding without verification
    here is exactly what an attacker would do.
    """
    token, _ = create_access_token(uuid.uuid4())
    payload = jwt.decode(token, options={"verify_signature": False})
    assert set(payload) == {"sub", "iat", "exp", "type"}


def test_token_signed_with_another_key_is_rejected() -> None:
    # 64 bytes: a *plausible* attacker key, not a short one. A key under 32 bytes
    # makes PyJWT warn, which would mean this test passed for the wrong reason.
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": 9999999999, "type": "access"},
        "a-different-secret-entirely-but-still-a-realistic-length-key-abcd",
        algorithm=ALGORITHM,
    )
    assert decode_access_token(forged) is None


def test_expired_token_is_rejected() -> None:
    expired = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": 1000000000, "iat": 999999999, "type": "access"},
        get_settings().secret_key,
        algorithm=ALGORITHM,
    )
    assert decode_access_token(expired) is None


def test_token_of_the_wrong_type_is_rejected() -> None:
    """Guards against replaying a token minted for another purpose.

    Correctly signed and unexpired — it fails purely on the `type` claim. Without
    that check, a future password-reset or email-verification token would be
    accepted as an access token.
    """
    wrong_type = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": 9999999999, "type": "password-reset"},
        get_settings().secret_key,
        algorithm=ALGORITHM,
    )
    assert decode_access_token(wrong_type) is None


def test_token_missing_required_claims_is_rejected() -> None:
    no_subject = jwt.encode(
        {"exp": 9999999999, "type": "access"}, get_settings().secret_key, algorithm=ALGORITHM
    )
    assert decode_access_token(no_subject) is None


def test_garbage_is_rejected() -> None:
    assert decode_access_token("not.a.jwt") is None
    assert decode_access_token("") is None


def test_refresh_tokens_are_unique_and_long() -> None:
    tokens = {generate_refresh_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(t) >= 40 for t in tokens)


def test_refresh_token_hash_is_deterministic_and_hides_the_token() -> None:
    token = generate_refresh_token()
    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert token not in hash_refresh_token(token)
    assert len(hash_refresh_token(token)) == 64
