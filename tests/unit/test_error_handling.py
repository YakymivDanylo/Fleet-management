import logging

import httpx

from fleet_management.config import Settings
from fleet_management.exceptions import NotFoundError
from fleet_management.main import create_app

SECRET_MARKER = "super-secret-internal-detail"


def build_app(**overrides):
    values = {
        "database_url": "postgresql+asyncpg://u:p@db:5432/fleet_sandbox",
        "jwt_secret_key": "s" * 40,
        **overrides,
    }
    app = create_app(Settings(_env_file=None, **values))

    @app.get("/boom")
    async def boom():
        raise RuntimeError(SECRET_MARKER)

    @app.get("/missing")
    async def missing():
        raise NotFoundError("nope")

    return app


def production_app():
    return build_app(
        app_env="production",
        database_url="postgresql+asyncpg://u:p@db:5432/fleet_production",
    )


def client_for(app) -> httpx.AsyncClient:
    # raise_app_exceptions=False: behave like a real server, which returns the 500 response.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_unexpected_error_returns_generic_500_without_traceback(caplog):
    async with client_for(production_app()) as client:
        with caplog.at_level(logging.ERROR):
            response = await client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"]
    assert SECRET_MARKER not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text


async def test_traceback_is_logged_server_side_with_the_same_request_id(caplog):
    async with client_for(production_app()) as client:
        with caplog.at_level(logging.ERROR):
            response = await client.get("/boom")

    request_id = response.json()["request_id"]
    records = [r for r in caplog.records if request_id in r.getMessage()]
    assert records
    assert records[0].exc_info is not None
    assert SECRET_MARKER in str(records[0].exc_info[1])


async def test_sandbox_without_debug_hides_traceback_too():
    async with client_for(build_app(debug=False)) as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert SECRET_MARKER not in response.text


async def test_debug_mode_shows_starlette_debug_page_only_when_enabled():
    # DEBUG=true is a sandbox-only convenience: Starlette then renders the traceback page.
    async with client_for(build_app(debug=True)) as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert SECRET_MARKER in response.text


async def test_domain_errors_keep_their_status_codes():
    async with client_for(build_app()) as client:
        response = await client.get("/missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "nope"}


async def test_api_docs_are_disabled_in_production():
    async with client_for(production_app()) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await client.get(path)).status_code == 404, path


async def test_api_docs_are_available_in_sandbox():
    async with client_for(build_app()) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await client.get(path)).status_code == 200, path


def test_debug_flag_follows_settings():
    assert build_app(debug=True).debug is True
    assert production_app().debug is False
