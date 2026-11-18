from ..exceptions import StationFullError, VehicleNotAvailableError
from .contracts import AuditPort, FleetPort, LedgerPort, RenterPort, StationPort
from .records import RentalRecord


class RentalLifecycleService:
    """Single responsibility: start and finish a rental (state transitions only)."""

    def __init__(
        self,
        renters: RenterPort,
        fleet: FleetPort,
        stations: StationPort,
        ledger: LedgerPort,
        audit: AuditPort,
    ):
        self._renters = renters
        self._fleet = fleet
        self._stations = stations
        self._ledger = ledger
        self._audit = audit

    def start_rental(self, renter_id: int, vehicle_id: int) -> RentalRecord:
        self._renters.get(renter_id)
        vehicle = self._fleet.get(vehicle_id)
        if not vehicle.available:
            raise VehicleNotAvailableError(f"Vehicle {vehicle_id} is not available")
        rental = self._ledger.open(renter_id, vehicle_id, vehicle.station_id)
        vehicle.available = False
        self._stations.undock(vehicle.station_id)
        self._audit.record("rental_started", rental_id=rental.id, vehicle_id=vehicle_id)
        return rental

    def end_rental(self, rental_id: int, end_station_id: int) -> RentalRecord:
        rental = self._ledger.get(rental_id)
        vehicle = self._fleet.get(rental.vehicle_id)
        if not self._stations.has_free_slot(end_station_id, vehicle.vehicle_type):
            raise StationFullError(f"Station {end_station_id} has no free slots")
        self._ledger.close(rental_id, end_station_id)
        vehicle.available = True
        vehicle.station_id = end_station_id
        self._stations.dock(end_station_id)
        self._audit.record("rental_ended", rental_id=rental_id, station_id=end_station_id)
        return rental
