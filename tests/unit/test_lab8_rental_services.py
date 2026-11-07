"""Behaviour of the decomposed Lab 8 services (same scenarios as the former God Object)."""

from datetime import UTC, datetime, timedelta

import pytest

from fleet_management.exceptions import NotFoundError, StationFullError, VehicleNotAvailableError
from fleet_management.lab8.records import RenterRecord, VehicleRecord
from fleet_management.lab8.wiring import RentalSystem, build_rental_system

RENTERS = {
    1: RenterRecord(1, "a@example.com"),
    2: RenterRecord(2, "vip@example.com", is_vip=True),
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def system() -> RentalSystem:
    vehicles = [VehicleRecord(1, "car", 1), VehicleRecord(2, "premium", 1)]
    built = build_rental_system({1: 2, 2: 1}, vehicles, list(RENTERS.values()))
    built.stations.dock(1)
    built.stations.dock(1)
    return built


def _finish(system: RentalSystem, rental_id: int, hours: float, station: int = 2):
    system.lifecycle.end_rental(rental_id, station)
    rental = system.ledger.get(rental_id)
    rental.ended_at = rental.started_at + timedelta(hours=hours)
    return rental


def _renter(_system: RentalSystem, renter_id: int) -> RenterRecord:
    return RENTERS[renter_id]


def test_start_rental_marks_vehicle_busy(system):
    rental = system.lifecycle.start_rental(1, 1)
    assert rental.vehicle_id == 1
    assert system.fleet.get(1).available is False


def test_start_rental_rejects_busy_vehicle(system):
    system.lifecycle.start_rental(1, 1)
    with pytest.raises(VehicleNotAvailableError):
        system.lifecycle.start_rental(2, 1)


def test_start_rental_unknown_renter(system):
    with pytest.raises(NotFoundError):
        system.lifecycle.start_rental(99, 1)


def test_end_rental_rejects_full_station(system):
    first = system.lifecycle.start_rental(1, 1)
    second = system.lifecycle.start_rental(2, 2)
    system.lifecycle.end_rental(first.id, 2)
    with pytest.raises(StationFullError):
        system.lifecycle.end_rental(second.id, 2)


def test_quote_applies_vip_discount(system):
    invoice = system.billing.quote(_renter(system, 2), "car", 2)
    assert (invoice.subtotal, invoice.discount, invoice.total) == (10.0, 1.0, 9.0)


def test_invoice_uses_billable_hours_and_vehicle_rate(system):
    rental = _finish(system, system.lifecycle.start_rental(1, 2).id, hours=1.5)
    invoice = system.billing.invoice_for(rental, _renter(system, 1), "premium")
    assert (invoice.hours, invoice.subtotal, invoice.total) == (2, 18.0, 18.0)


def test_late_fee_counts_hours_over_allowance(system):
    rental = system.lifecycle.start_rental(1, 1)
    rental.started_at -= timedelta(hours=5)
    assert system.billing.late_fee(rental, _now(), allowed_hours=2) == 12.0


def test_notifications_reach_the_renter(system):
    rental = system.lifecycle.start_rental(1, 1)
    system.notifications.notify_started(rental)
    _finish(system, rental.id, hours=1)
    invoice = system.billing.invoice_for(rental, _renter(system, 1), "car")
    system.notifications.notify_finished(rental, invoice)
    subjects = [subject for _, subject, _ in system.mailer.outbox]
    assert subjects == ["Rental started", "Rental finished"]


def test_overdue_notification_only_when_fee_positive(system):
    rental = system.lifecycle.start_rental(1, 1)
    assert system.notifications.notify_overdue(rental, fee=0.0) is False
    rental.started_at -= timedelta(hours=6)
    fee = system.billing.late_fee(rental, _now(), allowed_hours=2)
    assert system.notifications.notify_overdue(rental, fee) is True


def test_reports_aggregate_finished_rentals(system):
    rental = _finish(system, system.lifecycle.start_rental(1, 2).id, hours=1)
    assert system.reporting.daily_report(rental.ended_at.date()) == {"rentals": 1, "revenue": 9.0}
    assert system.reporting.revenue_by_vehicle_type() == {"premium": 9.0}
    assert [r.id for r in system.ledger.for_renter(1)] == [rental.id]


def test_services_work_with_any_object_that_satisfies_the_contracts(system):
    """Dependency inversion: swap the ledger-backed mailer for a fake without touching services."""

    class FakeMailer:
        def __init__(self):
            self.sent = []

        def send(self, to, subject, body):
            self.sent.append(subject)

    from fleet_management.lab8.infrastructure import RenterDirectory
    from fleet_management.lab8.notifications import NotificationService

    fake = FakeMailer()
    rental = system.lifecycle.start_rental(1, 1)
    NotificationService(RenterDirectory(list(RENTERS.values())), fake).notify_started(rental)
    assert fake.sent == ["Rental started"]
