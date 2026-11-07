"""Prometheus metrics (Lab 7): request counter + latency histogram, `/metrics`, FAIL_RATE.

Labels are low-cardinality on purpose: the *route template* (``/vehicles/{vehicle_id}``),
never the raw path, so ids cannot blow up the number of time series.
"""

import secrets
import time

from fastapi import HTTPException, Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Probes and the scrape itself would drown real traffic and must never be failed on purpose.
SKIPPED_PATHS = frozenset({"/metrics", "/health", "/livez"})
UNKNOWN_ROUTE = "unknown"
_RNG = secrets.SystemRandom()  # not a security decision; avoids a predictable PRNG

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["route"])


def route_template(scope: Scope) -> str:
    """Route pattern of the matched endpoint; 404s and unmatched paths share one label."""
    route = scope.get("route")
    return getattr(route, "path", None) or UNKNOWN_ROUTE


class MetricsMiddleware:
    """Counts requests and observes their duration (pure ASGI, no body access)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in SKIPPED_PATHS:
            await self.app(scope, receive, send)
            return

        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = route_template(scope)
            REQUESTS.labels(scope["method"], route, str(status_code)).inc()
            LATENCY.labels(route).observe(time.perf_counter() - started)


async def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def failure_injector(fail_rate: float):
    """Router-level dependency: answers a share `fail_rate` of requests with HTTP 500.

    Used to simulate a bad release (Lab 7, step 6). It runs after routing, so the failed
    request still carries its route template in metrics and logs.
    """

    async def inject_failure(request: Request) -> None:
        if fail_rate > 0 and request.url.path not in SKIPPED_PATHS:
            if _RNG.random() < fail_rate:
                raise HTTPException(status_code=500, detail="injected failure")

    return inject_failure
