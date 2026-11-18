"""Composition root: the only place that knows the concrete classes behind the contracts."""

from dataclasses import dataclass

from .billing import BillingService
from .contracts import FleetPort, LedgerPort, StationPort
from .infrastructure import (
    AuditLog,
    Clock,
    Mailer,
    RentalStore,
    RenterDirectory,
    StationRegistry,
    VehicleFleet,
)
from .lifecycle import RentalLifecycleService
from .notifications import NotificationService
from .records import RenterRecord, VehicleRecord
from .reporting import ReportingService
from .tariff import TariffCalculator


@dataclass(frozen=True)
class RentalSystem:
    lifecycle: RentalLifecycleService
    billing: BillingService
    notifications: NotificationService
    reporting: ReportingService
    ledger: LedgerPort
    fleet: FleetPort
    stations: StationPort
    mailer: Mailer


def build_rental_system(
    station_capacity: dict[int, int],
    vehicles: list[VehicleRecord],
    renters: list[RenterRecord],
) -> RentalSystem:
    clock, mailer, audit = Clock(), Mailer(), AuditLog()
    stations, fleet, directory = (
        StationRegistry(station_capacity),
        VehicleFleet(vehicles),
        RenterDirectory(renters),
    )
    ledger = RentalStore(clock)
    billing = BillingService(TariffCalculator())
    return RentalSystem(
        lifecycle=RentalLifecycleService(directory, fleet, stations, ledger, audit),
        billing=billing,
        notifications=NotificationService(directory, mailer),
        reporting=ReportingService(ledger, fleet, directory, billing),
        ledger=ledger,
        fleet=fleet,
        stations=stations,
        mailer=mailer,
    )
