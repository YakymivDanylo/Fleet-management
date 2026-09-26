from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import get_redis, get_retry_policy
from ..database import get_db
from ..models import Vehicle
from ..resilience import RetryPolicy
from ..schemas import VehicleCreate, VehicleRead, VehicleStateRead
from ..services import station_service, vehicle_state_service

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.post("", response_model=VehicleRead, status_code=201)
async def create_vehicle(payload: VehicleCreate, db: AsyncSession = Depends(get_db)):
    await station_service.get_station(db, payload.station_id)

    vehicle = Vehicle(
        license_plate=payload.license_plate,
        model=payload.model,
        station_id=payload.station_id,
    )
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle


@router.get("", response_model=list[VehicleRead])
async def list_vehicles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Vehicle))
    return result.scalars().all()


@router.get("/{vehicle_id}", response_model=VehicleRead)
async def get_vehicle(vehicle_id: int, db: AsyncSession = Depends(get_db)):
    vehicle = await db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


@router.get("/{vehicle_id}/state", response_model=VehicleStateRead)
async def get_vehicle_state(
    vehicle_id: int,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    policy: RetryPolicy | None = Depends(get_retry_policy),
):
    return await vehicle_state_service.get_vehicle_state(db, redis, vehicle_id, policy)
