class DomainError(Exception):
    """Base class for fleet management domain errors."""


class NotFoundError(DomainError):
    """Raised when a referenced entity does not exist."""


class VehicleNotAvailableError(DomainError):
    """Raised when a vehicle cannot be rented in its current state."""


class StationFullError(DomainError):
    """Raised when a station has no free capacity for a returning vehicle."""


class DependencyUnavailableError(DomainError):
    """Raised when a dependency failed and no degraded answer can be produced."""


class EmailAlreadyRegisteredError(DomainError):
    """Raised when a user tries to register with an email that is already taken."""


class ConsentDeniedError(DomainError):
    """Raised by the consent policy gate when a consent-dependent action must not run."""

    def __init__(self, purpose: str, reason: str) -> None:
        super().__init__(f"Consent for {purpose} denied: {reason}")
        self.purpose = purpose
        self.reason = reason
