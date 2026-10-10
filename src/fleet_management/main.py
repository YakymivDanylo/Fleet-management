import logging
import socket
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .api import router as api_router
from .cache import close_redis
from .config import Settings, settings
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
logger = logging.getLogger(__name__)


def _build_lifespan(cfg: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not cfg.jwt_secret_key:
            raise RuntimeError("JWT_SECRET_KEY is not set; the API cannot issue access tokens")
        yield
        await close_redis()

    return lifespan


def _register_error_handlers(app: FastAPI) -> None:
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

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        # The traceback goes to the server log only; the client gets a generic body
        # plus an id that lets support find the matching log entry.
        request_id = uuid.uuid4().hex
        logger.error(
            "Unhandled error [request_id=%s] on %s %s",
            request_id,
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )


def _register_service_routes(app: FastAPI) -> None:
    @app.get("/livez")
    async def liveness_check():
        return {"status": "alive"}

    @app.get("/info")
    async def app_info():
        return {
            "app": app.state.settings.app_name,
            "version": app.state.settings.app_version,
            "pod": socket.gethostname(),
        }

    @app.get("/health")
    async def health_check(db: AsyncSession = Depends(get_db)):
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}


def create_app(cfg: Settings = settings) -> FastAPI:
    # Production hides the interactive API docs and never runs in debug mode, so neither
    # the schema nor Starlette's debug traceback page is exposed to the public.
    docs_enabled = not cfg.is_production
    app = FastAPI(
        title=cfg.app_name,
        debug=cfg.debug,
        lifespan=_build_lifespan(cfg),
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.settings = cfg
    app.include_router(api_router)
    _register_error_handlers(app)
    _register_service_routes(app)
    return app


app = create_app()
