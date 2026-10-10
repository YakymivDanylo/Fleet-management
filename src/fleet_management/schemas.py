from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import RentalStatus, UserRole, VehicleStatus


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


class VehicleStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vehicle_id: int
    recorded_at: datetime
    latitude: float
    longitude: float
    fuel_level: float
    is_locked: bool
    source: Literal["cache", "database"]
    degraded: bool = False


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=150)
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9 ()-]{7,20}$")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    phone: str | None = None
    role: UserRole
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    role: UserRole
    home_url: str
