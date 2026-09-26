from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..exceptions import EmailAlreadyRegisteredError
from ..models import User, UserRole
from ..security import hash_password, verify_password

# Verified when the email is unknown, so a login for a missing account takes as
# long as one with a wrong password and response time does not reveal which emails exist.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing")


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == normalize_email(email)))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str,
    role: UserRole = UserRole.USER,
) -> User:
    user = User(
        email=normalize_email(email),
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        # The unique index is the source of truth: a pre-check SELECT would still
        # race with a concurrent registration of the same email.
        await db.rollback()
        raise EmailAlreadyRegisteredError(f"Email {user.email} is already registered") from exc
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, user.hashed_password) or not user.is_active:
        return None
    return user
