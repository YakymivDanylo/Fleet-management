from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from .config import settings

# Argon2id with the library's recommended parameters: memory-hard, so offline
# brute force of a leaked hash is expensive on GPUs as well.
_password_hash = PasswordHash.recommended()


class InvalidTokenError(Exception):
    """Raised when an access token is malformed, forged or expired."""


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return _password_hash.verify(password, hashed_password)


def create_access_token(user_id: int, role: str, expires_delta: timedelta | None = None) -> str:
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Return the user id stored in a valid token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            # Pinning the algorithm blocks "alg: none" and key-confusion attacks.
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError("Invalid or expired token") from exc
