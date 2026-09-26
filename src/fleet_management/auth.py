from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .models import User, UserRole
from .security import InvalidTokenError, decode_access_token

# tokenUrl makes the "Authorize" button in Swagger UI log in through /auth/login.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    try:
        user_id = decode_access_token(token)
    except InvalidTokenError:
        raise _UNAUTHORIZED from None

    # The role is read from the database, not from the token claim, so a demoted
    # or deactivated user loses access immediately instead of when the token expires.
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise _UNAUTHORIZED
    return user


def require_roles(*roles: UserRole) -> Callable[..., Coroutine[Any, Any, User]]:
    """Dependency factory: 401 for anonymous callers, 403 for authenticated ones without a role."""

    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return user

    return checker


require_admin = require_roles(UserRole.ADMIN)
require_user = require_roles(UserRole.USER)
