"""Seed data for the Lab 2 load test (stdlib only, runs from the host).

Creates one station with N vehicles through the public API, then publishes one
telemetry message per vehicle to RabbitMQ (via the management HTTP API). The
telemetry-worker stores each reading in Postgres and caches it in Redis - the
same path real telemetry takes - so both the cache and the fallback have data.

Usage:  python scripts/seed_loadtest.py [--vehicles 50]
"""

import argparse
import base64
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

API_URL = "http://localhost:8000"
RABBITMQ_API_URL = "http://localhost:15672/api/exchanges/%2F/amq.default/publish"
RABBITMQ_AUTH = base64.b64encode(b"guest:guest").decode()
PLATE_PREFIX = "LT-"


def request(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        req.add_header(name, value)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read() or b"null")


def ensure_vehicles(count: int) -> list[int]:
    existing = [
        v
        for v in request("GET", f"{API_URL}/vehicles")
        if v["license_plate"].startswith(PLATE_PREFIX)
    ]
    if len(existing) >= count:
        return [v["id"] for v in existing[:count]]

    station = request(
        "POST", f"{API_URL}/stations", {"address": "Lviv, Load Test 1", "capacity": count}
    )
    taken = {v["license_plate"] for v in existing}
    ids = [v["id"] for v in existing]
    number = 0
    while len(ids) < count:
        number += 1
        plate = f"{PLATE_PREFIX}{number:04d}"
        if plate in taken:
            continue
        vehicle = request(
            "POST",
            f"{API_URL}/vehicles",
            {"license_plate": plate, "model": "Renault Zoe", "station_id": station["id"]},
        )
        ids.append(vehicle["id"])
    return ids


def publish_telemetry(vehicle_id: int, recorded_at: str) -> None:
    payload = {
        "vehicle_id": vehicle_id,
        "recorded_at": recorded_at,
        "latitude": 49.84 + vehicle_id / 10000,
        "longitude": 24.03 + vehicle_id / 10000,
        "fuel_level": 40 + vehicle_id % 60,
        "is_locked": True,
    }
    result = request(
        "POST",
        RABBITMQ_API_URL,
        {
            "properties": {"delivery_mode": 2, "content_type": "application/json"},
            "routing_key": "telemetry",
            "payload": json.dumps(payload),
            "payload_encoding": "string",
        },
        headers={"Authorization": f"Basic {RABBITMQ_AUTH}"},
    )
    if not result.get("routed"):
        raise RuntimeError("Telemetry was not routed: is the telemetry-worker running?")


def wait_until_cached(vehicle_ids: list[int], timeout_seconds: float = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    pending = set(vehicle_ids)
    while pending and time.monotonic() < deadline:
        for vehicle_id in list(pending):
            try:
                state = request("GET", f"{API_URL}/vehicles/{vehicle_id}/state")
            except urllib.error.HTTPError:
                continue
            if state["source"] == "cache":
                pending.discard(vehicle_id)
        if pending:
            time.sleep(0.5)
    if pending:
        raise RuntimeError(
            f"Vehicles without cached state after {timeout_seconds}s: {sorted(pending)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vehicles", type=int, default=50)
    args = parser.parse_args()

    vehicle_ids = ensure_vehicles(args.vehicles)
    recorded_at = datetime.now(UTC).isoformat()
    for vehicle_id in vehicle_ids:
        publish_telemetry(vehicle_id, recorded_at)
    wait_until_cached(vehicle_ids)
    first, last = min(vehicle_ids), max(vehicle_ids)
    print(f"Seeded {len(vehicle_ids)} vehicles (ids {first}..{last}), all cached in Redis")


if __name__ == "__main__":
    main()
