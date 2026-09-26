from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import User, UserRole
from ..schemas import Token, UserRead, UserRegister
from ..security import create_access_token
from ..services import user_service
from .home import HOME_URLS

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=201)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    # The role is not part of the payload: self-registration always yields a
    # regular user, otherwise anyone could register themselves as an admin.
    return await user_service.create_user(
        db, payload.email, payload.password, payload.full_name, role=UserRole.USER
    )


@router.post("/login", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    # OAuth2 password flow names the field "username"; here it carries the email.
    user = await user_service.authenticate(db, form.username, form.password)
    if user is None:
        # One message for "no such email" and "wrong password" so the endpoint
        # cannot be used to find out which emails are registered.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(
        access_token=create_access_token(user.id, user.role),
        role=user.role,
        home_url=HOME_URLS[user.role],
    )


@router.get("/me", response_model=UserRead)
async def read_me(user: User = Depends(get_current_user)):
    return user
