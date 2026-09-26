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
