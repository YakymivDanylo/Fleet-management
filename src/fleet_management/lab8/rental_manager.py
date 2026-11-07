"""Baseline (FAIL-prone) design: one class owns lifecycle, billing, notifications and reports."""

from datetime import date

from ..exceptions import StationFullError, VehicleNotAvailableError
from .infrastructure import (
    AuditLog,
    Clock,
    Mailer,
    RentalStore,
    RenterDirectory,
    StationRegistry,
    VehicleFleet,
)
from .records import Invoice, RentalRecord, RenterRecord, VehicleRecord
from .tariff import FineCalculator, TariffCalculator


class RentalManager:
    def __init__(
        self,
        station_capacity: dict[int, int],
        vehicles: list[VehicleRecord],
        renters: list[RenterRecord],
    ):
        self.stations = StationRegistry(station_capacity)
        self.fleet = VehicleFleet(vehicles)
        self.renters = RenterDirectory(renters)
        self.store = RentalStore()
        self.mailer = Mailer()
        self.audit = AuditLog()
        self.clock = Clock()
        self.tariff = TariffCalculator()
        self.fines = FineCalculator()
        self.revenue_cache: dict[str, float] = {}

    # --- rental lifecycle -----------------------------------------------------------------
    def start_rental(self, renter_id: int, vehicle_id: int) -> RentalRecord:
        self.renters.get(renter_id)
        vehicle = self.fleet.get(vehicle_id)
        if not vehicle.available:
            raise VehicleNotAvailableError(f"Vehicle {vehicle_id} is not available")
        rental = RentalRecord(
            self.store.next_id(), renter_id, vehicle_id, vehicle.station_id, self.clock.now()
        )
        vehicle.available = False
        self.stations.undock(vehicle.station_id)
        self.store.add(rental)
        self.audit.record("rental_started", rental_id=rental.id, vehicle_id=vehicle_id)
        return rental

    def end_rental(self, rental_id: int, end_station_id: int) -> RentalRecord:
        rental = self.store.get(rental_id)
        if not self.stations.has_free_slot(end_station_id):
            raise StationFullError(f"Station {end_station_id} has no free slots")
        vehicle = self.fleet.get(rental.vehicle_id)
        rental.ended_at = self.clock.now()
        rental.end_station_id = end_station_id
        vehicle.available = True
        vehicle.station_id = end_station_id
        self.stations.dock(end_station_id)
        self.audit.record("rental_ended", rental_id=rental_id, station_id=end_station_id)
        return rental

    # --- billing --------------------------------------------------------------------------
    def quote(self, vehicle_type: str, hours: int, renter_id: int) -> Invoice:
        renter = self.renters.get(renter_id)
        subtotal = self.tariff.price(hours, vehicle_type)
        discount = self.tariff.discount(
            subtotal, renter.rental_count, renter.has_coupon, renter.is_vip
        )
        return Invoice(0, hours, subtotal, discount, round(subtotal - discount, 2))

    def build_invoice(self, rental_id: int) -> Invoice:
        rental = self.store.get(rental_id)
        vehicle = self.fleet.get(rental.vehicle_id)
        renter = self.renters.get(rental.renter_id)
        seconds = (rental.ended_at - rental.started_at).total_seconds()
        hours = self.tariff.billable_hours(seconds)
        subtotal = self.tariff.price(hours, vehicle.vehicle_type)
        discount = self.tariff.discount(
            subtotal, renter.rental_count, renter.has_coupon, renter.is_vip
        )
        self.audit.record("invoice_built", rental_id=rental_id, hours=hours)
        return Invoice(rental_id, hours, subtotal, discount, round(subtotal - discount, 2))

    def late_fee(self, rental_id: int, allowed_hours: int) -> float:
        rental = self.store.get(rental_id)
        elapsed = (self.clock.now() - rental.started_at).total_seconds()
        return self.fines.late_fee(self.tariff.billable_hours(elapsed) - allowed_hours)

    # --- notifications --------------------------------------------------------------------
    def notify_started(self, rental_id: int) -> None:
        rental = self.store.get(rental_id)
        renter = self.renters.get(rental.renter_id)
        self.mailer.send(renter.email, "Rental started", f"Rental {rental_id} is active")
        self.audit.record("mail_sent", kind="started", rental_id=rental_id)

    def notify_finished(self, rental_id: int) -> None:
        invoice = self.build_invoice(rental_id)
        renter = self.renters.get(self.store.get(rental_id).renter_id)
        self.mailer.send(renter.email, "Rental finished", f"Total: {invoice.total:.2f}")

    def notify_overdue(self, rental_id: int, allowed_hours: int) -> bool:
        fee = self.late_fee(rental_id, allowed_hours)
        if fee <= 0:
            return False
        renter = self.renters.get(self.store.get(rental_id).renter_id)
        self.mailer.send(renter.email, "Rental overdue", f"Late fee so far: {fee:.2f}")
        return True

    # --- reporting ------------------------------------------------------------------------
    def daily_report(self, day: date) -> dict[str, float]:
        finished = [r for r in self.store.all() if r.ended_at and r.ended_at.date() == day]
        revenue = sum(self.build_invoice(r.id).total for r in finished)
        self.revenue_cache[day.isoformat()] = revenue
        return {"rentals": len(finished), "revenue": round(revenue, 2)}

    def renter_history(self, renter_id: int) -> list[int]:
        self.renters.get(renter_id)
        return [r.id for r in self.store.all() if r.renter_id == renter_id]

    def revenue_by_vehicle_type(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for rental in self.store.all():
            if rental.ended_at is None:
                continue
            vehicle_type = self.fleet.get(rental.vehicle_id).vehicle_type
            totals[vehicle_type] = totals.get(vehicle_type, 0) + self.build_invoice(rental.id).total
        return totals
