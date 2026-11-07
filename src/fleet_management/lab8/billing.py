from datetime import datetime

from .contracts import TariffPort
from .records import Invoice, RentalRecord, RenterRecord

DEFAULT_ZONE = "city"


class BillingService:
    """Single responsibility: turn rentals into money. Knows the tariff only through its port."""

    def __init__(self, tariff: TariffPort):
        self._tariff = tariff

    def _invoice(
        self, rental_id: int, hours: int, vehicle_type: str, renter: RenterRecord
    ) -> Invoice:
        subtotal = self._tariff.price(hours, vehicle_type, DEFAULT_ZONE)
        discount = self._tariff.discount(
            subtotal, renter.rental_count, renter.has_coupon, renter.is_vip
        )
        return Invoice(rental_id, hours, subtotal, discount, round(subtotal - discount, 2))

    def quote(self, renter: RenterRecord, vehicle_type: str, hours: int) -> Invoice:
        return self._invoice(0, hours, vehicle_type, renter)

    def invoice_for(self, rental: RentalRecord, renter: RenterRecord, vehicle_type: str) -> Invoice:
        seconds = (rental.ended_at - rental.started_at).total_seconds()
        hours = self._tariff.billable_hours(seconds)
        return self._invoice(rental.id, hours, vehicle_type, renter)

    def late_fee(self, rental: RentalRecord, now: datetime, allowed_hours: int) -> float:
        elapsed = (now - rental.started_at).total_seconds()
        return self._tariff.late_fee(self._tariff.billable_hours(elapsed) - allowed_hours)
