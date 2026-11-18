from dataclasses import dataclass
from datetime import datetime


@dataclass
class VehicleRecord:
    id: int
    vehicle_type: str
    station_id: int
    available: bool = True


@dataclass
class RenterRecord:
    id: int
    email: str
    rental_count: int = 0
    has_coupon: bool = False
    is_vip: bool = False


@dataclass
class RentalRecord:
    id: int
    renter_id: int
    vehicle_id: int
    start_station_id: int
    started_at: datetime
    ended_at: datetime | None = None
    end_station_id: int | None = None


@dataclass(frozen=True)
class Invoice:
    rental_id: int
    hours: int
    subtotal: float
    discount: float
    total: float
