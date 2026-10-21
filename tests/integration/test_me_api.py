from httpx import AsyncClient

PASSWORD = "correct-horse-battery"


async def signup(client: AsyncClient, email: str) -> tuple[int, dict]:
    response = await client.post(
        "/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Test Renter"}
    )
    assert response.status_code == 201
    login = await client.post("/auth/login", data={"username": email, "password": PASSWORD})
    return response.json()["id"], {"Authorization": f"Bearer {login.json()['access_token']}"}


async def create_vehicle(client: AsyncClient, plate: str = "BC0001AA") -> int:
    station = await client.post("/stations", json={"address": "Main st", "capacity": 5})
    vehicle = await client.post(
        "/vehicles",
        json={"license_plate": plate, "model": "Zoe", "station_id": station.json()["id"]},
    )
    return vehicle.json()["id"]


async def add_renter_profile(client: AsyncClient, user_id: int, headers: dict, licence: str) -> int:
    response = await client.post(
        f"/api/users/{user_id}/renter-profile",
        json={"full_name": "Test Renter", "license_number": licence},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["renter_id"]


async def test_me_endpoints_require_authentication(client: AsyncClient):
    assert (await client.get("/me/renter")).status_code == 401
    assert (await client.get("/me/rentals")).status_code == 401


async def test_renter_profile_is_404_until_created(client: AsyncClient):
    user_id, headers = await signup(client, "a@example.com")
    assert (await client.get("/me/renter", headers=headers)).status_code == 404

    renter_id = await add_renter_profile(client, user_id, headers, "LIC-A")

    response = await client.get("/me/renter", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "id": renter_id,
        "full_name": "Test Renter",
        "license_number": "LIC-A",
    }


async def test_my_rentals_is_empty_without_renter_profile(client: AsyncClient):
    _, headers = await signup(client, "a@example.com")
    response = await client.get("/me/rentals", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_my_rentals_returns_only_own_rentals_with_accrued_cost(client: AsyncClient):
    user_a, headers_a = await signup(client, "a@example.com")
    user_b, headers_b = await signup(client, "b@example.com")
    renter_a = await add_renter_profile(client, user_a, headers_a, "LIC-A")
    renter_b = await add_renter_profile(client, user_b, headers_b, "LIC-B")
    vehicle_a = await create_vehicle(client, "BC0001AA")
    vehicle_b = await create_vehicle(client, "BC0002AA")
    await client.post("/rentals/start", json={"renter_id": renter_a, "vehicle_id": vehicle_a})
    await client.post("/rentals/start", json={"renter_id": renter_b, "vehicle_id": vehicle_b})

    rentals = (await client.get("/me/rentals", headers=headers_a)).json()

    assert [r["renter_id"] for r in rentals] == [renter_a]
    assert rentals[0]["status"] == "active"
    # Minimum billable hour applies to a rental that has just started.
    assert rentals[0]["cost"] == 5.0


async def test_rentals_list_includes_cost(client: AsyncClient):
    user_id, headers = await signup(client, "a@example.com")
    renter_id = await add_renter_profile(client, user_id, headers, "LIC-A")
    vehicle_id = await create_vehicle(client)
    rental = (
        await client.post("/rentals/start", json={"renter_id": renter_id, "vehicle_id": vehicle_id})
    ).json()
    await client.post(
        f"/rentals/{rental['id']}/end", json={"end_station_id": rental["start_station_id"]}
    )

    rentals = (await client.get("/rentals")).json()

    assert rentals[0]["status"] == "completed"
    assert rentals[0]["cost"] == 5.0
