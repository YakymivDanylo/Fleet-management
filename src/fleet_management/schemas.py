from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .models import RentalStatus, VehicleStatus


class StationCreate(BaseModel):
    address: str
    capacity: int


class StationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    address: str
    capacity: int


class RenterCreate(BaseModel):
    full_name: str
    license_number: str


class RenterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    license_number: str


class VehicleCreate(BaseModel):
    license_plate: str
    model: str
    station_id: int


class VehicleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    license_plate: str
    model: str
    status: VehicleStatus
    station_id: int


class RentalStart(BaseModel):
    renter_id: int
    vehicle_id: int


class RentalEnd(BaseModel):
    end_station_id: int


class RentalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    renter_id: int
    vehicle_id: int
    start_station_id: int
    end_station_id: int | None
    started_at: datetime
    ended_at: datetime | None
    status: RentalStatus
    cost: float | None = None
