"""Lab 11: ids outside PostgreSQL INTEGER get 422 (per contract), not a 500 from asyncpg."""

import httpx
import pytest

from fleet_management.main import app
from fleet_management.schemas import DB_ID_MAX

TOO_BIG = DB_ID_MAX + 1


def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.parametrize(
    "path",
    [
        f"/stations/{TOO_BIG}/availability",
        f"/stations/{TOO_BIG}",
        "/stations/0/availability",
        f"/vehicles/{TOO_BIG}/state",
        f"/vehicles/{TOO_BIG}",
        f"/rentals/{TOO_BIG}",
    ],
)
async def test_out_of_range_path_id_is_422(path):
    async with client() as c:
        response = await c.get(path)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][0] == "path"


@pytest.mark.parametrize(
    ("url", "body"),
    [
        ("/rentals/start", {"renter_id": 1, "vehicle_id": TOO_BIG}),
        ("/rentals/start", {"renter_id": 0, "vehicle_id": 1}),
        ("/rentals/1/end", {"end_station_id": TOO_BIG}),
        (f"/rentals/{TOO_BIG}/end", {"end_station_id": 1}),
    ],
)
async def test_out_of_range_ids_in_rental_requests_are_422(url, body):
    async with client() as c:
        response = await c.post(url, json=body)
    assert response.status_code == 422
