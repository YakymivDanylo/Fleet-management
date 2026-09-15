class DomainError(Exception):
    """Base class for fleet management domain errors."""


class NotFoundError(DomainError):
    """Raised when a referenced entity does not exist."""


class VehicleNotAvailableError(DomainError):
    """Raised when a vehicle cannot be rented in its current state."""


class StationFullError(DomainError):
    """Raised when a station has no free capacity for a returning vehicle."""
