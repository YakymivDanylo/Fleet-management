from datetime import timedelta

import jwt
import pytest

from fleet_management.config import settings
from fleet_management.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_does_not_store_plain_text():
    hashed = hash_password("s3cret-pass")

    assert hashed != "s3cret-pass"
    assert hashed.startswith("$argon2")


def test_hash_password_is_salted():
    assert hash_password("s3cret-pass") != hash_password("s3cret-pass")


def test_verify_password_accepts_correct_and_rejects_wrong():
    hashed = hash_password("s3cret-pass")

    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("wrong-pass", hashed)


def test_token_roundtrip_returns_user_id():
    token = create_access_token(42, "user")

    assert decode_access_token(token) == 42


def test_expired_token_is_rejected():
    token = create_access_token(42, "user", expires_delta=timedelta(seconds=-1))

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_token_signed_with_other_key_is_rejected():
    forged = jwt.encode(
        {"sub": "1", "role": "admin", "exp": 9999999999},
        "attacker-key-that-is-long-enough-for-hs256",
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(forged)


def test_unsigned_token_is_rejected():
    unsigned = jwt.encode({"sub": "1", "role": "admin", "exp": 9999999999}, None, algorithm="none")

    with pytest.raises(InvalidTokenError):
        decode_access_token(unsigned)


def test_token_without_subject_is_rejected():
    token = jwt.encode({"exp": 9999999999}, settings.jwt_secret_key, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)
