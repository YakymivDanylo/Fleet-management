import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .api import router as api_router
from .cache import close_redis
from .config import settings
from .database import get_db
from .exceptions import (
    DependencyUnavailableError,
    EmailAlreadyRegisteredError,
    NotFoundError,
    StationFullError,
    VehicleNotAvailableError,
)

DEPENDENCY_RETRY_AFTER_SECONDS = 5

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not set; the API cannot issue access tokens")
    yield
    await close_redis()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
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


@app.exception_handler(EmailAlreadyRegisteredError)
async def handle_email_taken(request: Request, exc: EmailAlreadyRegisteredError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(DependencyUnavailableError)
async def handle_dependency_unavailable(request: Request, exc: DependencyUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers={"Retry-After": str(DEPENDENCY_RETRY_AFTER_SECONDS)},
    )


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "connected"}
