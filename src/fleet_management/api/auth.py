from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import User, UserRole
from ..schemas import Token, UserRead, UserRegister
from ..security import create_access_token
from ..services import audit_service, user_service
from .home import HOME_URLS

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=201)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    return await user_service.create_user(
        db,
        payload.email,
        payload.password,
        payload.full_name,
        role=UserRole.USER,
        phone=payload.phone,
    )


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    username: Annotated[str, Form(description="Email користувача", examples=["petro@example.com"])],
    password: Annotated[str, Form(json_schema_extra={"format": "password"})],
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.authenticate(db, username, password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    await audit_service.record_activity(
        db,
        user.id,
        "login",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return Token(
        access_token=create_access_token(user.id, user.role),
        role=user.role,
        home_url=HOME_URLS[user.role],
    )


@router.get("/me", response_model=UserRead)
async def read_me(user: User = Depends(get_current_user)):
    return user
