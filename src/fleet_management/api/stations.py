from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import TypeAdapter
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import STATIONS_LIST_KEY, get_redis, invalidate, read_through_json
from ..database import get_db
from ..models import Station
from ..schemas import StationCreate, StationRead

router = APIRouter(prefix="/stations", tags=["stations"])

_stations_adapter = TypeAdapter(list[StationRead])


@router.post("", response_model=StationRead, status_code=201)
async def create_station(
    payload: StationCreate,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    station = Station(address=payload.address, capacity=payload.capacity)
    db.add(station)
    await db.commit()
    await db.refresh(station)
    await invalidate(redis, STATIONS_LIST_KEY)
    return station


@router.get("", response_model=list[StationRead])
async def list_stations(db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    async def load():
        result = await db.execute(select(Station).order_by(Station.id))
        return result.scalars().all()

    body = await read_through_json(redis, STATIONS_LIST_KEY, _stations_adapter, load)
    return Response(content=body, media_type="application/json")


@router.get("/{station_id}", response_model=StationRead)
async def get_station(station_id: int, db: AsyncSession = Depends(get_db)):
    station = await db.get(Station, station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    return station
