import json
import logging

import httpx
from fastapi import FastAPI
from prometheus_client import REGISTRY

from fleet_management.config import Settings
from fleet_management.main import app, create_app
from fleet_management.privacy import middleware as access_log
from fleet_management.privacy.logging_setup import JsonSanitizingFormatter


def make_client(application: FastAPI = app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test")


def sample(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def test_metrics_endpoint_exposes_prometheus_text():
    async with make_client() as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in response.text


async def test_request_is_counted_with_route_template_and_status():
    labels = {"method": "GET", "route": "/version", "status": "200"}
    before = sample("http_requests_total", **labels)
    async with make_client() as client:
        await client.get("/version")
    assert sample("http_requests_total", **labels) == before + 1
    assert sample("http_request_duration_seconds_count", route="/version") >= 1


async def test_unknown_paths_share_one_label_value():
    labels = {"method": "GET", "route": "unknown", "status": "404"}
    before = sample("http_requests_total", **labels)
    async with make_client() as client:
        await client.get("/no/such/path/1")
        await client.get("/no/such/path/2")
    assert sample("http_requests_total", **labels) == before + 2


async def test_probes_and_scrape_are_not_counted():
    before = sum(
        s.value for m in REGISTRY.collect() if m.name == "http_requests" for s in m.samples
    )
    async with make_client() as client:
        await client.get("/livez")
        await client.get("/metrics")
    after = sum(s.value for m in REGISTRY.collect() if m.name == "http_requests" for s in m.samples)
    assert after == before


def failing_app(rate: float) -> FastAPI:
    return create_app(Settings(database_url=app.state.settings.database_url, fail_rate=rate))


async def test_fail_rate_one_answers_500_but_keeps_probes_healthy():
    async with make_client(failing_app(1.0)) as client:
        assert (await client.get("/version")).status_code == 500
        assert (await client.get("/livez")).status_code == 200


async def test_fail_rate_zero_never_fails():
    async with make_client(failing_app(0.0)) as client:
        codes = [(await client.get("/version")).status_code for _ in range(20)]
    assert set(codes) == {200}


async def test_injected_failure_is_counted_under_its_route():
    labels = {"method": "GET", "route": "/version", "status": "500"}
    before = sample("http_requests_total", **labels)
    async with make_client(failing_app(1.0)) as client:
        await client.get("/version")
    assert sample("http_requests_total", **labels) == before + 1


async def test_access_log_line_is_json_with_structured_fields():
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Capture()
    access_log.logger.addHandler(handler)
    access_log.logger.setLevel(logging.INFO)
    try:
        async with make_client(failing_app(1.0)) as client:
            await client.get("/version")
    finally:
        access_log.logger.removeHandler(handler)

    line = json.loads(JsonSanitizingFormatter().format(records[-1]))
    assert line["level"] == "ERROR"
    assert line["method"] == "GET"
    assert line["route"] == "/version"
    assert line["status"] == 500
    assert isinstance(line["duration_ms"], float)
    assert line["version"]
    assert "timestamp" in line and "message" in line


def test_fail_rate_is_validated():
    import pytest

    with pytest.raises(ValueError):
        Settings(database_url=app.state.settings.database_url, fail_rate=1.5)
