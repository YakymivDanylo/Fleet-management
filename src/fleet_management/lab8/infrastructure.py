from datetime import UTC, datetime

from ..exceptions import NotFoundError
from .records import RentalRecord, RenterRecord, VehicleRecord


class StationRegistry:
    def __init__(self, capacity: dict[int, int]):
        self._capacity = dict(capacity)
        self._docked: dict[int, int] = {station: 0 for station in capacity}

    def has_free_slot(self, station_id: int, vehicle_type: str) -> bool:
        """A slot is free for the given vehicle type (per-type slot policy, e.g. EV chargers)."""
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


class Clock:
    def now(self) -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)


class RentalStore:  # implements LedgerPort
    def __init__(self, clock: Clock):
        self._clock = clock
        self._rentals: dict[int, RentalRecord] = {}
        self._next_id = 1

    def open(self, renter_id: int, vehicle_id: int, station_id: int) -> RentalRecord:
        rental = RentalRecord(self._next_id, renter_id, vehicle_id, station_id, self._clock.now())
        self._next_id += 1
        self._rentals[rental.id] = rental
        return rental

    def close(self, rental_id: int, station_id: int) -> RentalRecord:
        rental = self.get(rental_id)
        rental.ended_at = self._clock.now()
        rental.end_station_id = station_id
        return rental

    def get(self, rental_id: int) -> RentalRecord:
        if rental_id not in self._rentals:
            raise NotFoundError(f"Rental {rental_id} not found")
        return self._rentals[rental_id]

    def all(self) -> list[RentalRecord]:
        return list(self._rentals.values())

    def for_renter(self, renter_id: int) -> list[RentalRecord]:
        return [r for r in self._rentals.values() if r.renter_id == renter_id]


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
