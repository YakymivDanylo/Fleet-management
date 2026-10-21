"""Endpoints scoped to the logged-in account: its renter profile and its own rentals."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..exceptions import NotFoundError
from ..models import Rental, Renter, User
from ..schemas import RentalRead, RenterRead
from .rentals import rental_with_cost

router = APIRouter(prefix="/me", tags=["me"])


async def _renter_of(db: AsyncSession, user: User) -> Renter | None:
    result = await db.execute(select(Renter).where(Renter.user_id == user.id))
    return result.scalar_one_or_none()


@router.get("/renter", response_model=RenterRead)
async def my_renter_profile(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    renter = await _renter_of(db, user)
    if renter is None:
        raise NotFoundError("Renter profile not found")
    return renter


@router.get("/rentals", response_model=list[RentalRead])
async def my_rentals(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    renter = await _renter_of(db, user)
    if renter is None:
        return []
    result = await db.execute(
        select(Rental).where(Rental.renter_id == renter.id).order_by(Rental.started_at.desc())
    )
    return [rental_with_cost(rental) for rental in result.scalars().all()]
