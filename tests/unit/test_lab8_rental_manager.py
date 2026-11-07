"""Behaviour of the Lab 8 God Object (RentalManager) - the baseline that must stay green."""

from datetime import timedelta

import pytest

from fleet_management.exceptions import NotFoundError, StationFullError, VehicleNotAvailableError
from fleet_management.lab8.records import RenterRecord, VehicleRecord
from fleet_management.lab8.rental_manager import RentalManager


@pytest.fixture
def manager() -> RentalManager:
    vehicles = [VehicleRecord(1, "car", 1), VehicleRecord(2, "premium", 1)]
    renters = [RenterRecord(1, "a@example.com"), RenterRecord(2, "vip@example.com", is_vip=True)]
    mgr = RentalManager({1: 2, 2: 1}, vehicles, renters)
    mgr.stations.dock(1)
    mgr.stations.dock(1)
    return mgr


def _finish(mgr: RentalManager, rental_id: int, hours: float, station: int = 2) -> None:
    mgr.end_rental(rental_id, station)
    rental = mgr.store.get(rental_id)
    rental.ended_at = rental.started_at + timedelta(hours=hours)


def test_start_rental_marks_vehicle_busy(manager):
    rental = manager.start_rental(1, 1)
    assert rental.vehicle_id == 1
    assert manager.fleet.get(1).available is False


def test_start_rental_rejects_busy_vehicle(manager):
    manager.start_rental(1, 1)
    with pytest.raises(VehicleNotAvailableError):
        manager.start_rental(2, 1)


def test_start_rental_unknown_renter(manager):
    with pytest.raises(NotFoundError):
        manager.start_rental(99, 1)


def test_end_rental_rejects_full_station(manager):
    first = manager.start_rental(1, 1)
    second = manager.start_rental(2, 2)
    manager.end_rental(first.id, 2)
    with pytest.raises(StationFullError):
        manager.end_rental(second.id, 2)


def test_quote_applies_vip_discount(manager):
    invoice = manager.quote("car", 2, renter_id=2)
    assert (invoice.subtotal, invoice.discount, invoice.total) == (10.0, 1.0, 9.0)


def test_invoice_uses_billable_hours_and_vehicle_rate(manager):
    rental = manager.start_rental(1, 2)
    _finish(manager, rental.id, hours=1.5)
    invoice = manager.build_invoice(rental.id)
    assert (invoice.hours, invoice.subtotal, invoice.total) == (2, 18.0, 18.0)


def test_late_fee_counts_hours_over_allowance(manager):
    rental = manager.start_rental(1, 1)
    rental.started_at -= timedelta(hours=5)
    assert manager.late_fee(rental.id, allowed_hours=2) == 12.0


def test_notifications_reach_the_renter(manager):
    rental = manager.start_rental(1, 1)
    manager.notify_started(rental.id)
    _finish(manager, rental.id, hours=1)
    manager.notify_finished(rental.id)
    subjects = [subject for _, subject, _ in manager.mailer.outbox]
    assert subjects == ["Rental started", "Rental finished"]


def test_overdue_notification_only_when_fee_positive(manager):
    rental = manager.start_rental(1, 1)
    assert manager.notify_overdue(rental.id, allowed_hours=2) is False
    rental.started_at -= timedelta(hours=6)
    assert manager.notify_overdue(rental.id, allowed_hours=2) is True


def test_reports_aggregate_finished_rentals(manager):
    rental = manager.start_rental(1, 2)
    _finish(manager, rental.id, hours=1)
    day = manager.store.get(rental.id).ended_at.date()
    assert manager.daily_report(day) == {"rentals": 1, "revenue": 9.0}
    assert manager.revenue_by_vehicle_type() == {"premium": 9.0}
    assert manager.renter_history(1) == [rental.id]
