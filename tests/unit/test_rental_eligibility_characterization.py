"""Golden-master test: pins the behaviour of validate_rental_eligibility to the
pre-refactoring implementation (frozen copy below) over every input combination."""

from itertools import product

import pytest

from fleet_management.models import VehicleStatus
from fleet_management.services.rental_service import validate_rental_eligibility


def _legacy_validate_rental_eligibility(
    renter_is_blacklisted,
    license_expired,
    has_unpaid_fees,
    active_rental_count,
    vehicle_status,
    station_is_open,
    is_weekend,
    weekend_requires_deposit,
    has_deposit_on_file,
):
    if renter_is_blacklisted:
        return False, "Renter is blacklisted"
    if license_expired:
        return False, "License expired"

    deposit_missing = is_weekend and weekend_requires_deposit and not has_deposit_on_file

    if has_unpaid_fees:
        if active_rental_count > 0:
            return False, "Unpaid fees with an active rental"
        if deposit_missing:
            return False, "Deposit required for unpaid fees on weekend"

    if vehicle_status != VehicleStatus.AVAILABLE:
        return False, "Vehicle not available"
    if not station_is_open:
        return False, "Station is closed"
    if deposit_missing:
        return False, "Deposit required on weekend"

    return True, "OK"


BOOL = (False, True)
ALL_INPUTS = list(product(BOOL, BOOL, BOOL, (0, 1, 3), list(VehicleStatus), BOOL, BOOL, BOOL, BOOL))


def test_input_space_is_fully_enumerated():
    assert len(ALL_INPUTS) == 2**7 * 3 * len(VehicleStatus)


@pytest.mark.parametrize("args", ALL_INPUTS)
def test_matches_legacy_behaviour(args):
    assert validate_rental_eligibility(*args) == _legacy_validate_rental_eligibility(*args)
