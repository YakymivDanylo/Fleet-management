import httpx

from fleet_management.main import app


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_root_redirects_to_ui():
    async with make_client() as client:
        response = await client.get("/")
    assert response.status_code == 307
    assert response.headers["location"] == "/app/"


async def test_ui_index_is_served():
    async with make_client() as client:
        response = await client.get("/app/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'src="js/app.js"' in response.text


async def test_ui_assets_are_served():
    async with make_client() as client:
        script = await client.get("/app/js/app.js")
        style = await client.get("/app/css/app.css")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert style.status_code == 200
