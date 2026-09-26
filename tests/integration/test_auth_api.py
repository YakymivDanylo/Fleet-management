import pytest
from httpx import AsyncClient

from fleet_management.models import UserRole
from fleet_management.services import user_service

PASSWORD = "correct-horse-battery"


async def register(client: AsyncClient, email: str = "renter@example.com", **overrides):
    payload = {"email": email, "password": PASSWORD, "full_name": "Test Renter", **overrides}
    return await client.post("/auth/register", json=payload)


async def login(client: AsyncClient, email: str, password: str = PASSWORD):
    return await client.post("/auth/login", data={"username": email, "password": password})


async def auth_headers(client: AsyncClient, email: str) -> dict:
    response = await login(client, email)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def user_headers(client: AsyncClient) -> dict:
    assert (await register(client)).status_code == 201
    return await auth_headers(client, "renter@example.com")


@pytest.fixture
async def admin_headers(client: AsyncClient, session_factory) -> dict:
    async with session_factory() as db:
        await user_service.create_user(
            db, "admin@example.com", PASSWORD, "Admin", role=UserRole.ADMIN
        )
    return await auth_headers(client, "admin@example.com")


# --- registration -----------------------------------------------------------


async def test_register_creates_regular_user(client: AsyncClient):
    response = await register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "renter@example.com"
    assert body["role"] == "user"
    assert "password" not in body
    assert "hashed_password" not in body


async def test_register_ignores_role_in_payload(client: AsyncClient):
    response = await register(client, role="admin")

    assert response.status_code == 201
    assert response.json()["role"] == "user"


async def test_register_duplicate_email_is_conflict(client: AsyncClient):
    await register(client)

    response = await register(client, email="Renter@Example.com")

    assert response.status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [{"email": "not-an-email"}, {"password": "short"}, {"full_name": ""}],
)
async def test_register_rejects_invalid_payload(client: AsyncClient, overrides: dict):
    response = await register(client, **overrides)

    assert response.status_code == 422


# --- login ------------------------------------------------------------------


async def test_login_returns_token_and_user_home(client: AsyncClient):
    await register(client)

    response = await login(client, "renter@example.com")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "user"
    assert body["home_url"] == "/home/user"


async def test_admin_login_points_to_admin_home(client: AsyncClient, admin_headers):
    response = await login(client, "admin@example.com")

    assert response.status_code == 200
    assert response.json()["home_url"] == "/home/admin"


async def test_login_wrong_password_is_unauthorized(client: AsyncClient):
    await register(client)

    response = await login(client, "renter@example.com", "wrong-password")

    assert response.status_code == 401


async def test_login_unknown_email_gives_same_error(client: AsyncClient):
    await register(client)

    wrong_password = await login(client, "renter@example.com", "wrong-password")
    unknown_email = await login(client, "ghost@example.com")

    assert unknown_email.status_code == 401
    assert unknown_email.json() == wrong_password.json()


async def test_me_returns_current_user(client: AsyncClient, user_headers):
    response = await client.get("/auth/me", headers=user_headers)

    assert response.status_code == 200
    assert response.json()["email"] == "renter@example.com"


# --- anonymous and invalid tokens --------------------------------------------


@pytest.mark.parametrize("path", ["/auth/me", "/home/user", "/home/admin", "/admin/users"])
async def test_protected_routes_reject_anonymous(client: AsyncClient, path: str):
    response = await client.get(path)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_garbage_token_is_unauthorized(client: AsyncClient):
    response = await client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"})

    assert response.status_code == 401


async def test_deactivated_user_loses_access(client: AsyncClient, user_headers, session_factory):
    async with session_factory() as db:
        user = await user_service.get_user_by_email(db, "renter@example.com")
        user.is_active = False
        await db.commit()

    response = await client.get("/auth/me", headers=user_headers)

    assert response.status_code == 401


# --- role-based home pages and admin panel ----------------------------------


async def test_user_home_page_for_user(client: AsyncClient, user_headers):
    response = await client.get("/home/user", headers=user_headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Кабінет орендаря" in response.text


async def test_admin_home_page_for_admin(client: AsyncClient, admin_headers):
    response = await client.get("/home/admin", headers=admin_headers)

    assert response.status_code == 200
    assert "Адмін-панель" in response.text


async def test_user_cannot_open_admin_home(client: AsyncClient, user_headers):
    response = await client.get("/home/admin", headers=user_headers)

    assert response.status_code == 403


async def test_user_cannot_open_admin_panel(client: AsyncClient, user_headers):
    response = await client.get("/admin/users", headers=user_headers)

    assert response.status_code == 403


async def test_admin_lists_users(client: AsyncClient, admin_headers, user_headers):
    response = await client.get("/admin/users", headers=admin_headers)

    assert response.status_code == 200
    assert {u["email"] for u in response.json()} == {"admin@example.com", "renter@example.com"}


async def test_admin_creates_another_admin(client: AsyncClient, admin_headers):
    payload = {"email": "second@example.com", "password": PASSWORD, "full_name": "Second"}

    response = await client.post("/admin/admins", json=payload, headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["role"] == "admin"


async def test_user_cannot_create_admin(client: AsyncClient, user_headers):
    payload = {"email": "evil@example.com", "password": PASSWORD, "full_name": "Evil"}

    response = await client.post("/admin/admins", json=payload, headers=user_headers)

    assert response.status_code == 403


async def test_home_page_escapes_user_name(client: AsyncClient):
    await register(client, full_name="<script>alert(1)</script>")
    headers = await auth_headers(client, "renter@example.com")

    response = await client.get("/home/user", headers=headers)

    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text
