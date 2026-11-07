from datetime import UTC, datetime

from ..exceptions import NotFoundError
from .records import RentalRecord, RenterRecord, VehicleRecord


class StationRegistry:
    def __init__(self, capacity: dict[int, int]):
        self._capacity = dict(capacity)
        self._docked: dict[int, int] = {station: 0 for station in capacity}

    def has_free_slot(self, station_id: int) -> bool:
        return self._docked[station_id] < self._capacity[station_id]

    def dock(self, station_id: int) -> None:
        self._docked[station_id] += 1

    def undock(self, station_id: int) -> None:
        self._docked[station_id] -= 1


class VehicleFleet:
    def __init__(self, vehicles: list[VehicleRecord]):
        self._vehicles = {v.id: v for v in vehicles}

    def get(self, vehicle_id: int) -> VehicleRecord:
        if vehicle_id not in self._vehicles:
            raise NotFoundError(f"Vehicle {vehicle_id} not found")
        return self._vehicles[vehicle_id]


class RenterDirectory:
    def __init__(self, renters: list[RenterRecord]):
        self._renters = {r.id: r for r in renters}

    def get(self, renter_id: int) -> RenterRecord:
        if renter_id not in self._renters:
            raise NotFoundError(f"Renter {renter_id} not found")
        return self._renters[renter_id]


class RentalStore:
    def __init__(self):
        self._rentals: dict[int, RentalRecord] = {}
        self._next_id = 1

    def next_id(self) -> int:
        rental_id, self._next_id = self._next_id, self._next_id + 1
        return rental_id

    def add(self, rental: RentalRecord) -> None:
        self._rentals[rental.id] = rental

    def get(self, rental_id: int) -> RentalRecord:
        if rental_id not in self._rentals:
            raise NotFoundError(f"Rental {rental_id} not found")
        return self._rentals[rental_id]

    def all(self) -> list[RentalRecord]:
        return list(self._rentals.values())


class Mailer:
    def __init__(self):
        self.outbox: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.outbox.append((to, subject, body))


class AuditLog:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def record(self, event: str, **fields) -> None:
        self.events.append((event, fields))


class Clock:
    def now(self) -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)
