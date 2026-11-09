"""Abstract contracts (ports) that the Lab 8 services depend on instead of concrete classes."""

from datetime import date, datetime
from typing import Protocol

from .records import Invoice, RentalRecord, RenterRecord, VehicleRecord


class StationPort(Protocol):
    def has_free_slot(self, station_id: int, vehicle_type: str) -> bool: ...

    def dock(self, station_id: int) -> None: ...

    def undock(self, station_id: int) -> None: ...


class FleetPort(Protocol):
    def get(self, vehicle_id: int) -> VehicleRecord: ...


class RenterPort(Protocol):
    def get(self, renter_id: int) -> RenterRecord: ...


class LedgerPort(Protocol):
    def open(self, renter_id: int, vehicle_id: int, station_id: int) -> RentalRecord: ...

    def close(self, rental_id: int, station_id: int) -> RentalRecord: ...

    def get(self, rental_id: int) -> RentalRecord: ...

    def all(self) -> list[RentalRecord]: ...

    def for_renter(self, renter_id: int) -> list[RentalRecord]: ...


class AuditPort(Protocol):
    def record(self, event: str, **fields) -> None: ...


class MailPort(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class TariffPort(Protocol):
    def price(self, hours: int, vehicle_type: str, zone: str) -> float: ...

    def discount(
        self, subtotal: float, rental_count: int, has_coupon: bool, is_vip: bool
    ) -> float: ...

    def billable_hours(self, seconds: float) -> int: ...

    def late_fee(self, hours_over: int) -> float: ...


class BillingPort(Protocol):
    def invoice_for(
        self, rental: RentalRecord, renter: RenterRecord, vehicle_type: str
    ) -> Invoice: ...


class ReportPort(Protocol):
    def daily_report(self, day: date) -> dict[str, float]: ...

    def revenue_by_vehicle_type(self) -> dict[str, float]: ...


class ClockPort(Protocol):
    def now(self) -> datetime: ...
