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


@router.get("/{rental_id}", response_model=RentalRead)
async def get_rental(rental_id: int, db: AsyncSession = Depends(get_db)):
    rental = await db.get(Rental, rental_id)
    if rental is None:
        raise HTTPException(status_code=404, detail="Rental not found")
    return rental


@router.get("/summary")
async def rentals_summary(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Rental))
    rentals = result.scalars().all()

    active_count = 0
    completed_count = 0
    cancelled_count = 0
    total_revenue = 0.0

    for rental in rentals:
        if rental.status == RentalStatus.ACTIVE:
            active_count += 1
        elif rental.status == RentalStatus.COMPLETED:
            completed_count += 1
            if rental.ended_at is not None:
                duration_hours = (rental.ended_at - rental.started_at).total_seconds() / 3600
                if duration_hours < 1:
                    billable_hours = 1
                else:
                    if duration_hours == int(duration_hours):
                        billable_hours = int(duration_hours)
                    else:
                        billable_hours = int(duration_hours) + 1
                total_revenue += billable_hours * 5.0
        elif rental.status == RentalStatus.CANCELLED:
            cancelled_count += 1

    return {
        "active": active_count,
        "completed": completed_count,
        "cancelled": cancelled_count,
        "total_revenue": round(total_revenue, 2),
    }
