import random
from datetime import UTC, datetime

from fleet_management.telemetry.simulator import (
    HUBS,
    SimVehicle,
    advance,
    distance_m,
    station_hub,
    sync_fleet,
    to_message,
)

START = HUBS["right"][0]


def make_vehicle(status: str = "rented") -> SimVehicle:
    return SimVehicle(
        vehicle_id=1,
        station_id=1,
        status=status,
        latitude=START[0],
        longitude=START[1],
        heading=0.0,
        speed=0.0,
        fuel_level=50.0,
    )


def test_rented_vehicle_moves_and_uses_fuel():
    vehicle = make_vehicle("rented")
    advance(vehicle, 2.0, random.Random(1))

    moved = distance_m(*START, vehicle.latitude, vehicle.longitude)
    assert 13 < moved < 29  # 7..14 m/s for 2 s
    assert vehicle.fuel_level < 50.0


def test_parked_vehicle_stays_put_and_recharges():
    vehicle = make_vehicle("available")
    advance(vehicle, 2.0, random.Random(1))

    assert (vehicle.latitude, vehicle.longitude) == START
    assert vehicle.speed == 0.0
    assert vehicle.fuel_level > 50.0


def test_vehicle_heads_to_its_target_and_picks_a_new_one_on_arrival():
    vehicle = make_vehicle("rented")
    rng = random.Random(3)
    advance(vehicle, 2.0, rng)
    first_target = vehicle.target
    before = distance_m(vehicle.latitude, vehicle.longitude, *first_target)
    advance(vehicle, 2.0, rng)
    assert distance_m(vehicle.latitude, vehicle.longitude, *first_target) < before

    for _ in range(5000):
        advance(vehicle, 2.0, rng)
        if vehicle.target != first_target:
            break
    assert vehicle.target != first_target


def test_driving_vehicle_stays_on_its_river_bank():
    vehicle = make_vehicle("rented")
    rng = random.Random(7)
    right_bank_max_lon = max(lon for _, lon in HUBS["right"])
    for _ in range(3000):
        advance(vehicle, 2.0, rng)
        assert vehicle.longitude <= right_bank_max_lon + 0.001


def test_station_hub_is_deterministic():
    assert station_hub(3) == station_hub(3)
    assert station_hub(3) != station_hub(4)


def test_returned_vehicle_is_parked_at_its_new_station():
    rng = random.Random(1)
    fleet: dict[int, SimVehicle] = {}
    sync_fleet(fleet, [{"id": 1, "station_id": 1, "status": "rented"}], rng)
    for _ in range(50):
        advance(fleet[1], 2.0, rng)

    sync_fleet(fleet, [{"id": 1, "station_id": 2, "status": "available"}], rng)

    _, hub = station_hub(2)
    assert distance_m(*hub, fleet[1].latitude, fleet[1].longitude) < 100
    assert fleet[1].speed == 0.0
    assert fleet[1].target is None


def test_message_matches_worker_schema():
    message = to_message(make_vehicle("available"), datetime(2026, 10, 21, tzinfo=UTC))
    assert message.is_locked is True
    assert message.vehicle_id == 1
