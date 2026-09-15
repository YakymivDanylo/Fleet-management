from httpx import AsyncClient


async def create_station(client: AsyncClient, capacity: int = 5) -> dict:
    response = await client.post(
        "/stations", json={"address": "Lviv, Svobody 1", "capacity": capacity}
    )
    assert response.status_code == 201
    return response.json()


async def create_renter(client: AsyncClient, license_number: str = "LV-0001") -> dict:
    response = await client.post(
        "/renters", json={"full_name": "Test Renter", "license_number": license_number}
    )
    assert response.status_code == 201
    return response.json()


async def create_vehicle(client: AsyncClient, station_id: int, plate: str = "BC1234AA") -> dict:
    response = await client.post(
        "/vehicles",
        json={"license_plate": plate, "model": "Skoda Octavia", "station_id": station_id},
    )
    assert response.status_code == 201
    return response.json()


async def start_rental(client: AsyncClient, renter_id: int, vehicle_id: int):
    return await client.post(
        "/rentals/start", json={"renter_id": renter_id, "vehicle_id": vehicle_id}
    )


async def end_rental(client: AsyncClient, rental_id: int, end_station_id: int):
    return await client.post(f"/rentals/{rental_id}/end", json={"end_station_id": end_station_id})


async def get_vehicle(client: AsyncClient, vehicle_id: int) -> dict:
    response = await client.get(f"/vehicles/{vehicle_id}")
    assert response.status_code == 200
    return response.json()


async def test_health_reports_db_connected(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "connected"}


async def test_create_and_get_station(client: AsyncClient):
    station = await create_station(client, capacity=3)

    response = await client.get(f"/stations/{station['id']}")

    assert response.status_code == 200
    assert response.json() == {"id": station["id"], "address": "Lviv, Svobody 1", "capacity": 3}


async def test_get_missing_station_returns_404(client: AsyncClient):
    response = await client.get("/stations/999")

    assert response.status_code == 404


async def test_create_vehicle_for_missing_station_returns_404(client: AsyncClient):
    response = await client.post(
        "/vehicles", json={"license_plate": "BC0000AA", "model": "Tesla", "station_id": 999}
    )

    assert response.status_code == 404


async def test_new_vehicle_is_available(client: AsyncClient):
    station = await create_station(client)

    vehicle = await create_vehicle(client, station["id"])

    assert vehicle["status"] == "available"


async def test_start_rental_marks_vehicle_rented(client: AsyncClient):
    station = await create_station(client)
    renter = await create_renter(client)
    vehicle = await create_vehicle(client, station["id"])

    response = await start_rental(client, renter["id"], vehicle["id"])

    assert response.status_code == 201
    assert response.json()["status"] == "active"
    assert response.json()["start_station_id"] == station["id"]
    assert (await get_vehicle(client, vehicle["id"]))["status"] == "rented"


async def test_cannot_rent_already_rented_vehicle(client: AsyncClient):
    station = await create_station(client)
    first = await create_renter(client, "LV-0001")
    second = await create_renter(client, "LV-0002")
    vehicle = await create_vehicle(client, station["id"])
    await start_rental(client, first["id"], vehicle["id"])

    response = await start_rental(client, second["id"], vehicle["id"])

    assert response.status_code == 409


async def test_end_rental_completes_and_moves_vehicle(client: AsyncClient):
    start_station = await create_station(client)
    end_station = await create_station(client)
    renter = await create_renter(client)
    vehicle = await create_vehicle(client, start_station["id"])
    rental = (await start_rental(client, renter["id"], vehicle["id"])).json()

    response = await end_rental(client, rental["id"], end_station["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["end_station_id"] == end_station["id"]
    assert body["cost"] == 5.0
    vehicle_after = await get_vehicle(client, vehicle["id"])
    assert vehicle_after["status"] == "available"
    assert vehicle_after["station_id"] == end_station["id"]


async def test_end_rental_at_full_station_returns_409(client: AsyncClient):
    start_station = await create_station(client)
    full_station = await create_station(client, capacity=1)
    await create_vehicle(client, full_station["id"], plate="BC0001AA")
    renter = await create_renter(client)
    vehicle = await create_vehicle(client, start_station["id"], plate="BC0002AA")
    rental = (await start_rental(client, renter["id"], vehicle["id"])).json()

    response = await end_rental(client, rental["id"], full_station["id"])

    assert response.status_code == 409


async def test_return_to_start_station_with_capacity_one(client: AsyncClient):
    station = await create_station(client, capacity=1)
    renter = await create_renter(client)
    vehicle = await create_vehicle(client, station["id"])
    rental = (await start_rental(client, renter["id"], vehicle["id"])).json()

    response = await end_rental(client, rental["id"], station["id"])

    assert response.status_code == 200


async def test_rentals_summary_counts_by_status(client: AsyncClient):
    station = await create_station(client)
    renter = await create_renter(client)
    vehicle = await create_vehicle(client, station["id"])
    await start_rental(client, renter["id"], vehicle["id"])

    response = await client.get("/rentals/summary")

    assert response.status_code == 200
    assert response.json() == {"active": 1, "completed": 0, "cancelled": 0, "total_revenue": 0}
