from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer

from .models import RentalStatus, UserRole, VehicleStatus

# Primary keys are PostgreSQL INTEGER (int4). Larger ids made asyncpg raise OverflowError, i.e.
# HTTP 500; the API contract (docs/api/openapi.yaml) bounds them to 1..2^31-1 and answers 422
# (drift found by the Schemathesis contract test, Lab 11).
DB_ID_MAX = 2_147_483_647
DbId = Annotated[int, Field(ge=1, le=DB_ID_MAX)]


class StationCreate(BaseModel):
    address: str
    capacity: int


class StationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    address: str
    capacity: int


class StationAvailability(BaseModel):
    station_id: int
    capacity: int
    parked_vehicles: int
    free_slots: int
    available_vehicles: int


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
    station_id: DbId


class VehicleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    license_plate: str
    model: str
    status: VehicleStatus
    station_id: int


class RentalStart(BaseModel):
    renter_id: DbId
    vehicle_id: DbId


class RentalEnd(BaseModel):
    end_station_id: DbId


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

    # Rental timestamps are stored as naive UTC (`DateTime` without time zone). The API contract
    # (docs/api/openapi.yaml, format: date-time) requires RFC 3339 with an offset, so naive values
    # are emitted as UTC instead of leaving the client to guess the zone (found by Schemathesis).
    @field_serializer("started_at", "ended_at")
    def _as_utc(self, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


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


class VehiclePositionRead(BaseModel):
    vehicle_id: int
    license_plate: str
    model: str
    status: VehicleStatus
    station_id: int
    recorded_at: datetime
    latitude: float
    longitude: float
    fuel_level: float
    is_locked: bool
    source: Literal["cache", "database"]


class FleetPositionsRead(BaseModel):
    positions: list[VehiclePositionRead]
    without_telemetry: list[int]
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
