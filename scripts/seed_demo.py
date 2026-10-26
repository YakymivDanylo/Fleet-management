"""Fills a running sandbox stack with demo data for a UI walkthrough. Safe to re-run.

    python scripts/seed_demo.py                 # API at http://localhost:8000
    API_URL=http://localhost:8001 python scripts/seed_demo.py

Creates stations, vehicles and three renter accounts. Two renters get an active rental
(their cars drive on the live map once the telemetry simulator runs), every renter gets
one completed trip so history and revenue are not empty. "petro" is left without an
active rental so a rental can be started live during the demo.

Stations are created first on purpose: the simulator pins station ids 1..N to Kyiv
metro hubs, so a fresh database gives the nicest map.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
# Sandbox-only demo accounts; never reuse this password anywhere real.
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo12345")

STATIONS = [
    ("вул. Хрещатик, 22", 8),
    ("пл. Українських Героїв, 1", 6),
    ("НСК «Олімпійський»", 6),
    ("Центральний вокзал", 10),
    ("Лук'янівська площа", 4),
]
VEHICLES = [
    ("AA1001KA", "Renault Zoe", 0),
    ("AA2002KA", "Tesla Model 3", 0),
    ("AA3003KA", "Nissan Leaf", 0),
    ("AA4004KA", "Škoda Octavia", 1),
    ("AA5005KA", "VW ID.3", 1),
    ("AA6006KA", "Toyota Corolla", 2),
    ("AA7007KA", "Hyundai Kona EV", 2),
    ("AA8008KA", "BMW i3", 3),
    ("AA9009KA", "Kia Niro", 3),
    ("AA1010KA", "Renault Megane", 4),
]
RENTERS = [
    # email, full name, licence, keep an active rental?
    ("petro@demo.ua", "Петро Водій", "DEMO-0001", False),
    ("maria@demo.ua", "Марія Коваль", "DEMO-0002", True),
    ("ivan@demo.ua", "Іван Мельник", "DEMO-0003", True),
]


def call(method, path, *, json_body=None, form=None, token=None):
    headers = {}
    data = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode()
    elif form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urllib.parse.urlencode(form).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(API_URL + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read() or b"null")


def ensure_stations() -> list[dict]:
    existing = {s["address"]: s for s in call("GET", "/stations")}
    stations = []
    for address, capacity in STATIONS:
        station = existing.get(address) or call(
            "POST", "/stations", json_body={"address": address, "capacity": capacity}
        )
        stations.append(station)
    return stations


def ensure_vehicles(stations: list[dict]) -> None:
    plates = {v["license_plate"] for v in call("GET", "/vehicles")}
    for plate, model, station_index in VEHICLES:
        if plate not in plates:
            call(
                "POST",
                "/vehicles",
                json_body={
                    "license_plate": plate,
                    "model": model,
                    "station_id": stations[station_index]["id"],
                },
            )


def ensure_renter(email: str, full_name: str, licence: str) -> tuple[str, int]:
    try:
        call(
            "POST",
            "/auth/register",
            json_body={"email": email, "password": DEMO_PASSWORD, "full_name": full_name},
        )
    except urllib.error.HTTPError as exc:
        if exc.code != 409:  # 409 = already registered on a previous run
            raise
    token = call("POST", "/auth/login", form={"username": email, "password": DEMO_PASSWORD})[
        "access_token"
    ]
    me = call("GET", "/auth/me", token=token)
    try:
        renter = call("GET", "/me/renter", token=token)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        call(
            "POST",
            f"/api/users/{me['id']}/renter-profile",
            json_body={"full_name": full_name, "license_number": licence},
            token=token,
        )
        renter = call("GET", "/me/renter", token=token)
    return token, renter["id"]


def available_vehicle() -> dict:
    for vehicle in call("GET", "/vehicles"):
        if vehicle["status"] == "available":
            return vehicle
    raise SystemExit("No available vehicles left to rent")


def ensure_rentals(token: str, renter_id: int, keep_active: bool) -> None:
    rentals = call("GET", "/me/rentals", token=token)
    if not any(r["status"] == "completed" for r in rentals):
        vehicle = available_vehicle()
        rental = call(
            "POST",
            "/rentals/start",
            json_body={"renter_id": renter_id, "vehicle_id": vehicle["id"]},
        )
        call(
            "POST",
            f"/rentals/{rental['id']}/end",
            json_body={"end_station_id": rental["start_station_id"]},
        )
    if keep_active and not any(r["status"] == "active" for r in rentals):
        vehicle = available_vehicle()
        call(
            "POST",
            "/rentals/start",
            json_body={"renter_id": renter_id, "vehicle_id": vehicle["id"]},
        )


def main() -> None:
    stations = ensure_stations()
    ensure_vehicles(stations)
    for email, full_name, licence, keep_active in RENTERS:
        token, renter_id = ensure_renter(email, full_name, licence)
        ensure_rentals(token, renter_id, keep_active)

    vehicles = call("GET", "/vehicles")
    rented = sum(v["status"] == "rented" for v in vehicles)
    print(f"Stations: {len(stations)}, vehicles: {len(vehicles)} ({rented} rented)")
    print(f"Renter logins (password {DEMO_PASSWORD!r}):")
    for email, *_ in RENTERS:
        print(f"  {email}")


if __name__ == "__main__":
    main()
