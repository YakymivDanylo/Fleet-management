"""Telemetry simulator: publishes vehicle readings to RabbitMQ the same way real trackers would.

Rented vehicles drive between city hubs, parked ones stay at their station. Messages go
through the normal pipeline (queue -> telemetry-worker -> Postgres + Redis), so the live
map shows exactly what the production path produces.

    python -m fleet_management.telemetry.simulator --api-url http://localhost:8000

The simulator reads the vehicle list from the public GET /vehicles endpoint and does not
need database credentials.
"""

import argparse
import asyncio
import json
import logging
import math
import os
import random
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime

import aio_pika

from .schemas import TelemetryMessage

logger = logging.getLogger("telemetry.simulator")

EARTH_RADIUS_M = 6_371_000
DRIVE_SPEED_MPS = (7.0, 14.0)
FUEL_USE_PER_KM = 0.6
FUEL_RECHARGE_PER_TICK = 0.05
STATION_SPREAD_M = 40
ARRIVAL_M = 25
REFRESH_EVERY_TICKS = 5

# Kyiv metro stations as hubs. Stations in the schema have no coordinates, so each one is
# pinned to a hub; driving cars hop between hubs of the same river bank, which keeps the
# straight-line legs on land instead of crossing the Dnipro.
HUBS: dict[str, list[tuple[float, float]]] = {
    "right": [
        (50.4501, 30.5241),  # Maidan Nezalezhnosti
        (50.4392, 30.5167),  # Ploshcha Ukrainskykh Heroiv
        (50.4325, 30.5165),  # Olimpiiska
        (50.4410, 30.4890),  # Vokzalna
        (50.4620, 30.4822),  # Lukianivska
        (50.4659, 30.5153),  # Kontraktova Ploshcha
        (50.4729, 30.5048),  # Tarasa Shevchenka
        (50.4864, 30.4979),  # Pochaina
        (50.5013, 30.4983),  # Obolon
        (50.4549, 30.4459),  # Shuliavska
        (50.4588, 30.4199),  # Beresteiska
        (50.4277, 30.5389),  # Pecherska
        (50.4130, 30.5244),  # Lybidska
        (50.4049, 30.5167),  # Demiivska
    ],
    "left": [
        (50.4518, 30.5982),  # Livoberezhna
        (50.4559, 30.6126),  # Darnytsia
        (50.4618, 30.6303),  # Chernihivska
        (50.4647, 30.6457),  # Lisova
        (50.3980, 30.6342),  # Pozniaky
        (50.3953, 30.6163),  # Osokorky
        (50.4013, 30.6526),  # Kharkivska
    ],
}
ALL_HUBS = [(bank, point) for bank, points in HUBS.items() for point in points]


@dataclass
class SimVehicle:
    vehicle_id: int
    station_id: int
    status: str
    latitude: float
    longitude: float
    heading: float
    speed: float
    fuel_level: float
    bank: str = "right"
    target: tuple[float, float] | None = None

    @property
    def driving(self) -> bool:
        return self.status == "rented"


def offset(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    """Moves a point by metres; equirectangular approximation is fine at city scale."""
    dlat = math.degrees(north_m / EARTH_RADIUS_M)
    dlon = math.degrees(east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    north = math.radians(lat2 - lat1) * EARTH_RADIUS_M
    east = math.radians(lon2 - lon1) * EARTH_RADIUS_M * math.cos(math.radians(lat1))
    return math.hypot(north, east)


def station_hub(station_id: int) -> tuple[str, tuple[float, float]]:
    """Deterministic hub (bank, point) for a station id."""
    return ALL_HUBS[(station_id - 1) % len(ALL_HUBS)]


def bearing_rad(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    north = math.radians(lat2 - lat1)
    east = math.radians(lon2 - lon1) * math.cos(math.radians(lat1))
    return math.atan2(east, north)


def park_at_station(vehicle: SimVehicle, rng: random.Random) -> None:
    vehicle.bank, (lat, lon) = station_hub(vehicle.station_id)
    vehicle.latitude, vehicle.longitude = offset(
        lat, lon, rng.uniform(-1, 1) * STATION_SPREAD_M, rng.uniform(-1, 1) * STATION_SPREAD_M
    )
    vehicle.speed = 0.0
    vehicle.target = None


def pick_target(vehicle: SimVehicle, rng: random.Random) -> tuple[float, float]:
    options = [
        hub
        for hub in HUBS[vehicle.bank]
        if distance_m(vehicle.latitude, vehicle.longitude, *hub) > ARRIVAL_M * 4
    ]
    return rng.choice(options)


def advance(vehicle: SimVehicle, dt: float, rng: random.Random) -> None:
    """One simulation step: drive a rented vehicle towards a hub, recharge a parked one."""
    if not vehicle.driving:
        vehicle.speed = 0.0
        vehicle.fuel_level = min(100.0, vehicle.fuel_level + FUEL_RECHARGE_PER_TICK)
        return

    if vehicle.target is None:
        vehicle.target = pick_target(vehicle, rng)
        vehicle.speed = rng.uniform(*DRIVE_SPEED_MPS)

    remaining = distance_m(vehicle.latitude, vehicle.longitude, *vehicle.target)
    step = min(vehicle.speed * dt, remaining)
    vehicle.heading = bearing_rad(vehicle.latitude, vehicle.longitude, *vehicle.target)
    vehicle.latitude, vehicle.longitude = offset(
        vehicle.latitude,
        vehicle.longitude,
        step * math.cos(vehicle.heading),
        step * math.sin(vehicle.heading),
    )
    vehicle.fuel_level = max(0.0, vehicle.fuel_level - FUEL_USE_PER_KM * step / 1000)
    if remaining - step <= ARRIVAL_M:
        vehicle.target = None  # arrived: next tick picks a new hub and speed


def to_message(vehicle: SimVehicle, now: datetime) -> TelemetryMessage:
    return TelemetryMessage(
        vehicle_id=vehicle.vehicle_id,
        recorded_at=now,
        latitude=round(vehicle.latitude, 6),
        longitude=round(vehicle.longitude, 6),
        fuel_level=round(vehicle.fuel_level, 1),
        is_locked=not vehicle.driving,
    )


def sync_fleet(fleet: dict[int, SimVehicle], vehicles: list[dict], rng: random.Random) -> None:
    """Applies the API's view of the fleet: new vehicles, rentals started or ended."""
    for data in vehicles:
        sim = fleet.get(data["id"])
        if sim is None:
            sim = SimVehicle(
                vehicle_id=data["id"],
                station_id=data["station_id"],
                status=data["status"],
                latitude=0.0,
                longitude=0.0,
                heading=rng.uniform(0, 2 * math.pi),
                speed=0.0,
                fuel_level=rng.uniform(40, 100),
            )
            fleet[sim.vehicle_id] = sim
            park_at_station(sim, rng)
            continue
        returned = sim.driving and data["status"] != "rented"
        sim.status = data["status"]
        sim.station_id = data["station_id"]
        if returned:
            park_at_station(sim, rng)


def fetch_vehicles(api_url: str) -> list[dict]:
    with urllib.request.urlopen(f"{api_url.rstrip('/')}/vehicles", timeout=5) as response:
        return json.load(response)


async def run(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    fleet: dict[int, SimVehicle] = {}

    connection = await aio_pika.connect_robust(args.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(args.queue, durable=True)
        tick = 0
        while True:
            if tick % REFRESH_EVERY_TICKS == 0:
                try:
                    vehicles = await asyncio.to_thread(fetch_vehicles, args.api_url)
                    sync_fleet(fleet, vehicles, rng)
                except OSError as exc:
                    logger.warning("Could not refresh vehicle list: %s", exc)

            now = datetime.now(UTC)
            for vehicle in fleet.values():
                advance(vehicle, args.interval, rng)
                body = to_message(vehicle, now).model_dump_json().encode()
                await channel.default_exchange.publish(
                    aio_pika.Message(body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                    routing_key=args.queue,
                )
            driving = sum(v.driving for v in fleet.values())
            logger.info("Published %d readings (%d driving)", len(fleet), driving)
            tick += 1
            await asyncio.sleep(args.interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish simulated vehicle telemetry.")
    parser.add_argument("--api-url", default=os.getenv("API_URL", "http://localhost:8000"))
    parser.add_argument(
        "--rabbitmq-url", default=os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    )
    parser.add_argument("--queue", default=os.getenv("TELEMETRY_QUEUE", "telemetry"))
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between readings")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
