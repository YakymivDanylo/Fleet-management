import socket
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
    ConsentDeniedError,
    DependencyUnavailableError,
    EmailAlreadyRegisteredError,
    NotFoundError,
    StationFullError,
    VehicleNotAvailableError,
)
from .privacy import configure_logging
from .privacy.middleware import CorrelationIdMiddleware

DEPENDENCY_RETRY_AFTER_SECONDS = 5

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not set; the API cannot issue access tokens")
    yield
    await close_redis()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
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


@app.exception_handler(ConsentDeniedError)
async def handle_consent_denied(request: Request, exc: ConsentDeniedError):
    return JSONResponse(
        status_code=403,
        content={"decision": "DENY", "purpose": exc.purpose, "reason": exc.reason},
    )


@app.exception_handler(DependencyUnavailableError)
async def handle_dependency_unavailable(request: Request, exc: DependencyUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers={"Retry-After": str(DEPENDENCY_RETRY_AFTER_SECONDS)},
    )


@app.get("/livez")
async def liveness_check():
    return {"status": "alive"}


@app.get("/info")
async def app_info():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "pod": socket.gethostname(),
    }


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "connected"}
