import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from .config import settings

_password_hash = PasswordHash.recommended()

# Argon2 is deliberately slow (~60 ms of CPU). Called inline from an async handler it blocks the
# event loop, so every other request waits behind each login. argon2-cffi releases the GIL, so
# a small thread pool lets the loop keep serving while the hash is computed.
_hash_executor = (
    ThreadPoolExecutor(max_workers=settings.password_hash_workers, thread_name_prefix="argon2")
    if settings.password_hash_workers > 0
    else None
)


class InvalidTokenError(Exception):
    """Raised when an access token is malformed, forged or expired."""


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return _password_hash.verify(password, hashed_password)


async def hash_password_async(password: str) -> str:
    if _hash_executor is None:
        return hash_password(password)
    return await asyncio.get_running_loop().run_in_executor(_hash_executor, hash_password, password)


async def verify_password_async(password: str, hashed_password: str) -> bool:
    if _hash_executor is None:
        return verify_password(password, hashed_password)
    return await asyncio.get_running_loop().run_in_executor(
        _hash_executor, verify_password, password, hashed_password
    )


def create_access_token(user_id: int, role: str, expires_delta: timedelta | None = None) -> str:
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError("Invalid or expired token") from exc
