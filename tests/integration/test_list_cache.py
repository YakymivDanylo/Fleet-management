import pytest
from httpx import AsyncClient
from redis import exceptions as redis_errors

from fleet_management.cache import STATIONS_LIST_KEY, VEHICLES_LIST_KEY, get_redis
from fleet_management.main import app


async def make_station(client: AsyncClient, address: str = "Lviv, Main 1") -> dict:
    response = await client.post("/stations", json={"address": address, "capacity": 5})
    assert response.status_code == 201
    return response.json()


async def make_vehicle(client: AsyncClient, station_id: int, plate: str = "AA0001AA") -> dict:
    response = await client.post(
        "/vehicles", json={"license_plate": plate, "model": "Tesla 3", "station_id": station_id}
    )
    assert response.status_code == 201
    return response.json()


class DownRedis:
    async def get(self, *args, **kwargs):
        raise redis_errors.ConnectionError("down")

    set = delete = get


async def test_stations_list_is_cached_with_ttl(client: AsyncClient, redis_client):
    await make_station(client)

    first = await client.get("/stations")
    assert first.status_code == 200
    assert await redis_client.exists(STATIONS_LIST_KEY) == 1
    assert 0 < await redis_client.ttl(STATIONS_LIST_KEY) <= 30

    second = await client.get("/stations")
    assert second.json() == first.json()


async def test_creating_a_station_invalidates_the_cached_list(client: AsyncClient):
    await make_station(client, "Lviv, Main 1")
    assert len((await client.get("/stations")).json()) == 1

    await make_station(client, "Lviv, Main 2")

    assert len((await client.get("/stations")).json()) == 2


async def test_vehicle_list_reflects_rental_status_changes(client: AsyncClient, redis_client):
    station = await make_station(client)
    vehicle = await make_vehicle(client, station["id"])
    renter = (
        await client.post("/renters", json={"full_name": "A B", "license_number": "L1"})
    ).json()
    assert (await client.get("/vehicles")).json()[0]["status"] == "available"
    assert await redis_client.exists(VEHICLES_LIST_KEY) == 1

    rental = await client.post(
        "/rentals/start", json={"renter_id": renter["id"], "vehicle_id": vehicle["id"]}
    )
    assert rental.status_code == 201
    assert (await client.get("/vehicles")).json()[0]["status"] == "rented"

    ended = await client.post(
        f"/rentals/{rental.json()['id']}/end", json={"end_station_id": station["id"]}
    )
    assert ended.status_code == 200
    assert (await client.get("/vehicles")).json()[0]["status"] == "available"


async def test_lists_still_work_when_redis_is_down(client: AsyncClient):
    station = await make_station(client)
    app.dependency_overrides[get_redis] = lambda: DownRedis()

    response = await client.get("/stations")

    assert response.status_code == 200
    assert response.json()[0]["id"] == station["id"]


@pytest.mark.parametrize("path", ["/stations", "/vehicles"])
async def test_empty_lists_are_cached_as_empty_arrays(client: AsyncClient, path):
    assert (await client.get(path)).json() == []
    assert (await client.get(path)).json() == []
