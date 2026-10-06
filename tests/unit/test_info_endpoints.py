import httpx

from fleet_management.main import app


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_livez_does_not_need_dependencies():
    async with make_client() as client:
        response = await client.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_info_reports_version_and_pod():
    async with make_client() as client:
        body = (await client.get("/info")).json()
    assert set(body) == {"app", "version", "pod"}
    assert body["pod"]
