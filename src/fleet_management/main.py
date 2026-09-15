from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .api import router as api_router
from .config import settings
from .database import get_db
from .exceptions import NotFoundError, StationFullError, VehicleNotAvailableError

app = FastAPI(title=settings.app_name)
app.include_router(api_router)


@app.exception_handler(NotFoundError)
async def handle_not_found(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(VehicleNotAvailableError)
async def handle_vehicle_unavailable(request: Request, exc: VehicleNotAvailableError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(StationFullError)
async def handle_station_full(request: Request, exc: StationFullError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "connected"}
