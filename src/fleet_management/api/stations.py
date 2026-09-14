from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Station
from ..schemas import StationCreate, StationRead

router = APIRouter(prefix="/stations", tags=["stations"])


@router.post("", response_model=StationRead, status_code=201)
async def create_station(payload: StationCreate, db: AsyncSession = Depends(get_db)):
    station = Station(address=payload.address, capacity=payload.capacity)
    db.add(station)
    await db.commit()
    await db.refresh(station)
    return station


@router.get("", response_model=list[StationRead])
async def list_stations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Station))
    return result.scalars().all()


@router.get("/{station_id}", response_model=StationRead)
async def get_station(station_id: int, db: AsyncSession = Depends(get_db)):
    station = await db.get(Station, station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    return station
