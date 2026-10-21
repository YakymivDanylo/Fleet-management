"""Browser UI: a static single-page app served by the API itself (same origin, no CORS)."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"
UI_PATH = "/app"


def mount_ui(app: FastAPI) -> None:
    app.mount(UI_PATH, StaticFiles(directory=STATIC_DIR, html=True), name="ui")

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(f"{UI_PATH}/")
