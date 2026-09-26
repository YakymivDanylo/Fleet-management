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
    # "cache" = hot state from Redis; "database" = last reading from Postgres.
    source: Literal["cache", "database"]
    # True when the answer is a fallback caused by a failed dependency.
    degraded: bool = False


class UserRegister(BaseModel):
    email: EmailStr
    # Upper bound keeps a single request from burning CPU on hashing a huge string.
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=150)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # Plain str on output: the address was validated on input, and re-validating
    # stored data here would turn one odd row into a 500 for the whole list.
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    role: UserRole
    # Where the client should navigate after login: each role has its own home page.
    home_url: str
