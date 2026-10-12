"""Shared helpers for the privacy-engineering integration tests (synthetic data only)."""

from dataclasses import dataclass

from httpx import AsyncClient
from sqlalchemy import text

from fleet_management.models import UserRole
from fleet_management.services import user_service

PASSWORD = "synthetic-Passw0rd-123"  # gitleaks:allow

ALICE = {
    "email": "alice.synthetic@example.com",
    "full_name": "Alice Synthetic",
    "phone": "+380000000012",
    "license": "SYN-LIC-ALICE-0001",
}
BOB = {
    "email": "bob.synthetic@example.com",
    "full_name": "Bob Synthetic",
    "phone": "+380000000034",
    "license": "SYN-LIC-BOB-0002",
}
ADMIN = {"email": "admin.synthetic@example.com", "full_name": "Admin Synthetic"}


@dataclass
class Account:
    id: int
    headers: dict
    profile: dict


async def login_headers(client: AsyncClient, email: str) -> dict:
    response = await client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_account(client: AsyncClient, profile: dict) -> Account:
    response = await client.post(
        "/auth/register",
        json={
            "email": profile["email"],
            "password": PASSWORD,
            "full_name": profile["full_name"],
            "phone": profile["phone"],
        },
    )
    assert response.status_code == 201, response.text
    headers = await login_headers(client, profile["email"])
    return Account(response.json()["id"], headers, profile)


async def create_admin(session_factory, client: AsyncClient) -> dict:
    async with session_factory() as db:
        await user_service.create_user(
            db, ADMIN["email"], PASSWORD, ADMIN["full_name"], role=UserRole.ADMIN
        )
    return await login_headers(client, ADMIN["email"])


async def create_fleet(client: AsyncClient) -> tuple[int, int]:
    station = (await client.post("/stations", json={"address": "Test St 1", "capacity": 5})).json()
    vehicle = (
        await client.post(
            "/vehicles",
            json={"license_plate": "SYN-001", "model": "Synthetic EV", "station_id": station["id"]},
        )
    ).json()
    return station["id"], vehicle["id"]


async def seed_full_profile(client: AsyncClient, account: Account, vehicle_id: int) -> int:
    """Gives the account one record in every PII-bearing source; returns the rental id."""
    response = await client.post(
        f"/api/users/{account.id}/renter-profile",
        json={
            "full_name": account.profile["full_name"],
            "license_number": account.profile["license"],
        },
        headers=account.headers,
    )
    assert response.status_code == 201, response.text
    renter_id = response.json()["renter_id"]
    rental = await client.post(
        "/rentals/start", json={"renter_id": renter_id, "vehicle_id": vehicle_id}
    )
    assert rental.status_code == 201, rental.text
    for purpose in ("MARKETING_EMAIL", "OPTIONAL_ANALYTICS"):
        granted = await client.post(
            f"/api/users/{account.id}/consents/{purpose}/grant",
            json={"policy_version": "2026-01", "source": "web"},
            headers=account.headers,
        )
        assert granted.status_code == 200, granted.text
    queued = await client.post(
        f"/api/users/{account.id}/marketing-email",
        json={"campaign": "spring"},
        headers=account.headers,
    )
    assert queued.status_code == 202, queued.text
    tracked = await client.post(
        f"/api/users/{account.id}/analytics-events",
        json={"event_name": "page_view"},
        headers=account.headers,
    )
    assert tracked.status_code == 201, tracked.text
    return rental.json()["id"]


async def scan_all_text_columns(session_factory, needles: list[str]) -> list[str]:
    """Returns 'table.column' for every text column that still contains one of the needles."""
    hits: list[str] = []
    async with session_factory() as db:
        columns = (
            await db.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "AND data_type IN ('character varying', 'text', 'USER-DEFINED')"
                )
            )
        ).all()
        for table, column in columns:
            for needle in needles:
                found = (
                    await db.execute(
                        text(f'SELECT 1 FROM "{table}" WHERE "{column}"::text ILIKE :n LIMIT 1'),
                        {"n": f"%{needle}%"},
                    )
                ).first()
                if found:
                    hits.append(f"{table}.{column}")
    return hits


async def table_counts(session_factory) -> dict[str, int]:
    async with session_factory() as db:
        tables = (
            (await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")))
            .scalars()
            .all()
        )
        return {
            table: (await db.execute(text(f'SELECT count(*) FROM "{table}"'))).scalar_one()
            for table in sorted(tables)
        }
