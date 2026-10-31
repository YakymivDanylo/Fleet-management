from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import TypeAdapter
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin
from ..cache import VEHICLES_LIST_KEY, get_redis, get_retry_policy, invalidate, read_through_json
from ..database import get_db
from ..models import Vehicle
from ..resilience import RetryPolicy
from ..schemas import FleetPositionsRead, VehicleCreate, VehicleRead, VehicleStateRead
from ..services import station_service, vehicle_state_service

router = APIRouter(prefix="/vehicles", tags=["vehicles"])

_vehicles_adapter = TypeAdapter(list[VehicleRead])


@router.post("", response_model=VehicleRead, status_code=201)
async def create_vehicle(
    payload: VehicleCreate,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    await station_service.get_station(db, payload.station_id)

    vehicle = Vehicle(
        license_plate=payload.license_plate,
        model=payload.model,
        station_id=payload.station_id,
    )
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    await invalidate(redis, VEHICLES_LIST_KEY)
    return vehicle


@router.get("", response_model=list[VehicleRead])
async def list_vehicles(db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    async def load():
        result = await db.execute(select(Vehicle).order_by(Vehicle.id))
        return result.scalars().all()

    body = await read_through_json(redis, VEHICLES_LIST_KEY, _vehicles_adapter, load)
    return Response(content=body, media_type="application/json")


# Declared before /{vehicle_id} so "positions" is not parsed as an id.
# Admin-only: the position of a rented vehicle is the location of its renter.
@router.get("/positions", response_model=FleetPositionsRead, dependencies=[Depends(require_admin)])
async def fleet_positions(db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    return await vehicle_state_service.get_fleet_positions(db, redis)


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
