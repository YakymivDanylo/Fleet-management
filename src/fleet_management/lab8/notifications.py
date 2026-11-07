from .contracts import MailPort, RenterPort
from .records import Invoice, RentalRecord


class NotificationService:
    """Single responsibility: tell the renter what happened (data is passed in, not fetched)."""

    def __init__(self, renters: RenterPort, mailer: MailPort):
        self._renters = renters
        self._mailer = mailer

    def notify_started(self, rental: RentalRecord) -> None:
        renter = self._renters.get(rental.renter_id)
        self._mailer.send(renter.email, "Rental started", f"Rental {rental.id} is active")

    def notify_finished(self, rental: RentalRecord, invoice: Invoice) -> None:
        renter = self._renters.get(rental.renter_id)
        self._mailer.send(renter.email, "Rental finished", f"Total: {invoice.total:.2f}")

    def notify_overdue(self, rental: RentalRecord, fee: float) -> bool:
        if fee <= 0:
            return False
        renter = self._renters.get(rental.renter_id)
        self._mailer.send(renter.email, "Rental overdue", f"Late fee so far: {fee:.2f}")
        return True
