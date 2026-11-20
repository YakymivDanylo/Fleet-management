"""Lab 11: CORS is opt-in, only for the documentation site's Swagger UI "Try it out"."""

import httpx

from fleet_management.config import Settings
from fleet_management.main import create_app

DOCS_ORIGIN = "http://127.0.0.1:8001"


def build_app(**overrides):
    values = {
        "database_url": "postgresql+asyncpg://u:p@db:5432/fleet_sandbox",
        "jwt_secret_key": "s" * 40,
        **overrides,
    }
    return create_app(Settings(_env_file=None, **values))


async def preflight(app, origin: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.options(
            "/livez",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )


def test_origins_are_parsed_from_comma_separated_value():
    cfg = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@db:5432/fleet_sandbox",
        cors_allow_origins=" http://a.test , ,https://b.test",
    )
    assert cfg.cors_origins == ["http://a.test", "https://b.test"]


async def test_no_cors_headers_by_default():
    response = await preflight(build_app(), DOCS_ORIGIN)
    assert "access-control-allow-origin" not in response.headers


async def test_configured_docs_origin_is_allowed():
    response = await preflight(build_app(cors_allow_origins=DOCS_ORIGIN), DOCS_ORIGIN)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DOCS_ORIGIN


async def test_other_origins_stay_blocked():
    app = build_app(cors_allow_origins=DOCS_ORIGIN)
    response = await preflight(app, "https://evil.example")
    assert "access-control-allow-origin" not in response.headers
