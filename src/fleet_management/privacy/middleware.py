import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .correlation import accept_or_generate, correlation_id_var

CORRELATION_HEADER = "X-Correlation-ID"
_HEADER_KEY = CORRELATION_HEADER.lower().encode()
logger = logging.getLogger("fleet_management.access")


class CorrelationIdMiddleware:
    """Binds a correlation ID per request and writes a body-free access log line.

    Only method, path (no query string), status and duration are logged: request and
    response bodies are never read here, so PII in payloads cannot reach the logs.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(_HEADER_KEY, b"").decode("latin-1")
        correlation_id = accept_or_generate(incoming)
        token = correlation_id_var.set(correlation_id)
        status_code = 500
        started = time.perf_counter()

        async def send_with_header(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", []).append((_HEADER_KEY, correlation_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            app_state = getattr(scope.get("app"), "state", None)
            logger.log(
                logging.ERROR if status_code >= 500 else logging.INFO,
                "http_request method=%s path=%s status=%s duration_ms=%.1f",
                scope["method"],
                scope["path"],
                status_code,
                duration_ms,
                # Structured fields: with LOG_FORMAT=json they become keys of the JSON line.
                extra={
                    "method": scope["method"],
                    "route": getattr(scope.get("route"), "path", "unknown"),
                    "status": status_code,
                    "duration_ms": round(duration_ms, 1),
                    "version": getattr(getattr(app_state, "settings", None), "app_version", "dev"),
                },
            )
            correlation_id_var.reset(token)
