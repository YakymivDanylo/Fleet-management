from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Rental, RentalStatus
from ..schemas import RentalEnd, RentalRead, RentalStart
from ..services import rental_service

router = APIRouter(prefix="/rentals", tags=["rentals"])


@router.post("/start", response_model=RentalRead, status_code=201)
async def start_rental(payload: RentalStart, db: AsyncSession = Depends(get_db)):
    rental = await rental_service.start_rental(db, payload.renter_id, payload.vehicle_id)
    return rental


@router.post("/{rental_id}/end", response_model=RentalRead)
async def end_rental(rental_id: int, payload: RentalEnd, db: AsyncSession = Depends(get_db)):
    rental = await rental_service.end_rental(db, rental_id, payload.end_station_id)
    cost = rental_service.calculate_cost(rental.started_at, rental.ended_at)
    return RentalRead.model_validate(rental).model_copy(update={"cost": cost})


@router.get("", response_model=list[RentalRead])
async def list_rentals(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Rental))
    return result.scalars().all()


def _completed_rental_revenue(rental: Rental) -> float:
    if rental.ended_at is None:
        return 0.0
    return rental_service.calculate_cost(rental.started_at, rental.ended_at)


@router.get("/summary")
async def rentals_summary(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Rental))
    rentals = result.scalars().all()

    counts = Counter(rental.status for rental in rentals)
    total_revenue = sum(
        _completed_rental_revenue(rental)
        for rental in rentals
        if rental.status == RentalStatus.COMPLETED
    )

    return {
        "active": counts[RentalStatus.ACTIVE],
        "completed": counts[RentalStatus.COMPLETED],
        "cancelled": counts[RentalStatus.CANCELLED],
        "total_revenue": round(total_revenue, 2),
    }


@router.get("/{rental_id}", response_model=RentalRead)
async def get_rental(rental_id: int, db: AsyncSession = Depends(get_db)):
    rental = await db.get(Rental, rental_id)
    if rental is None:
        raise HTTPException(status_code=404, detail="Rental not found")
    return rental
