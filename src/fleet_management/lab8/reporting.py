from datetime import date

from .contracts import BillingPort, FleetPort, LedgerPort, RenterPort
from .records import RentalRecord


class ReportingService:
    """Single responsibility: read-only aggregates over finished rentals."""

    def __init__(
        self, ledger: LedgerPort, fleet: FleetPort, renters: RenterPort, billing: BillingPort
    ):
        self._ledger = ledger
        self._fleet = fleet
        self._renters = renters
        self._billing = billing

    def _priced(self, rental: RentalRecord) -> tuple[str, float]:
        vehicle_type = self._fleet.get(rental.vehicle_id).vehicle_type
        renter = self._renters.get(rental.renter_id)
        return vehicle_type, self._billing.invoice_for(rental, renter, vehicle_type).total

    def daily_report(self, day: date) -> dict[str, float]:
        finished = [r for r in self._ledger.all() if r.ended_at and r.ended_at.date() == day]
        revenue = sum(self._priced(r)[1] for r in finished)
        return {"rentals": len(finished), "revenue": round(revenue, 2)}

    def revenue_by_vehicle_type(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for rental in self._ledger.all():
            if rental.ended_at is not None:
                vehicle_type, total = self._priced(rental)
                totals[vehicle_type] = totals.get(vehicle_type, 0) + total
        return totals
