from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin
from ..database import get_db
from ..models import User, UserRole
from ..schemas import UserRead, UserRegister
from ..services import user_service

# The dependency on the router protects every current and future admin endpoint,
# so a new route cannot be left open by forgetting a per-route check.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/users", response_model=list[UserRead])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.id))
    return result.scalars().all()


@router.post("/admins", response_model=UserRead, status_code=201)
async def create_admin(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    return await user_service.create_user(
        db, payload.email, payload.password, payload.full_name, role=UserRole.ADMIN
    )
