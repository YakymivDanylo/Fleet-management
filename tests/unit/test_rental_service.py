from datetime import datetime, timedelta

import pytest

from fleet_management.models import VehicleStatus
from fleet_management.services.rental_service import (
    calculate_cost,
    calculate_discount,
    validate_rental_eligibility,
)

START = datetime(2026, 9, 15, 10, 0)


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (timedelta(minutes=0), 5.0),
        (timedelta(minutes=30), 5.0),
        (timedelta(hours=1), 5.0),
        (timedelta(hours=1, minutes=1), 10.0),
        (timedelta(hours=3), 15.0),
    ],
)
def test_calculate_cost_bills_started_hours_with_one_hour_minimum(duration, expected):
    assert calculate_cost(START, START + duration) == expected


def test_calculate_cost_uses_custom_rate():
    assert calculate_cost(START, START + timedelta(hours=2), rate_per_hour=7.5) == 15.0


def _discount(**overrides) -> float:
    params = {
        "rental_count": 0,
        "is_vip": False,
        "vehicle_type": "standard",
        "station_zones": [],
        "has_coupon": False,
        "is_weekend": False,
        "is_holiday": False,
    }
    params.update(overrides)
    return calculate_discount(**params)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"is_vip": True, "rental_count": 11, "vehicle_type": "premium"}, 5),
        ({"is_vip": True, "rental_count": 11}, 10),
        ({"is_vip": True, "rental_count": 3, "vehicle_type": "premium"}, 2),
        ({"is_vip": True, "rental_count": 3}, 5),
        ({"rental_count": 25}, 3),
        ({"rental_count": 10, "has_coupon": True}, 4),
        ({"rental_count": 10}, 1),
        ({"rental_count": 3}, 0),
        ({"is_weekend": True, "station_zones": ["center", "center", "suburb", "other"]}, 1),
        ({"station_zones": ["center"]}, 0),
        ({"is_holiday": True, "has_coupon": True}, 2),
        ({"is_holiday": True}, 1),
    ],
)
def test_calculate_discount(overrides, expected):
    assert _discount(**overrides) == expected


def _eligibility(**overrides) -> tuple[bool, str]:
    params = {
        "renter_is_blacklisted": False,
        "license_expired": False,
        "has_unpaid_fees": False,
        "active_rental_count": 0,
        "vehicle_status": VehicleStatus.AVAILABLE,
        "station_is_open": True,
        "is_weekend": False,
        "weekend_requires_deposit": False,
        "has_deposit_on_file": False,
    }
    params.update(overrides)
    return validate_rental_eligibility(**params)


WEEKEND_NO_DEPOSIT = {"is_weekend": True, "weekend_requires_deposit": True}


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, (True, "OK")),
        ({"renter_is_blacklisted": True}, (False, "Renter is blacklisted")),
        (
            {"renter_is_blacklisted": True, "license_expired": True},
            (False, "Renter is blacklisted"),
        ),
        ({"license_expired": True}, (False, "License expired")),
        (
            {"has_unpaid_fees": True, "active_rental_count": 1},
            (False, "Unpaid fees with an active rental"),
        ),
        (
            {"has_unpaid_fees": True, **WEEKEND_NO_DEPOSIT},
            (False, "Deposit required for unpaid fees on weekend"),
        ),
        ({"has_unpaid_fees": True}, (True, "OK")),
        ({"vehicle_status": VehicleStatus.RENTED}, (False, "Vehicle not available")),
        ({"station_is_open": False}, (False, "Station is closed")),
        (WEEKEND_NO_DEPOSIT, (False, "Deposit required on weekend")),
        ({**WEEKEND_NO_DEPOSIT, "has_deposit_on_file": True}, (True, "OK")),
    ],
)
def test_validate_rental_eligibility(overrides, expected):
    assert _eligibility(**overrides) == expected
