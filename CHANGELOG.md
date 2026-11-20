# Changelog

All notable changes to this project, newest first. Entries are grouped by UTC date.

## 2026-11-20

### Publish documentation site and API contract — 11:33 UTC
**Summary:** All project documentation now lives on one searchable website that rebuilds itself, and the public API has an official, tested description.
**Details:** Documentation is organised in four levels (overview, developer, API, architecture) with owners and review dates, published automatically and blocked when a link or page is broken. The public API is described in a contract that powers interactive docs and a client library. Checking it against the running system fixed wrong time formats and server errors on invalid or unknown ids.

## 2026-11-14

### Add station availability and system documentation passport — 08:43 UTC
**Summary:** Anyone can now see how many free parking spots and free cars a station has, and the system finally has up-to-date design, infrastructure and handover documents.
**Details:** New read-only endpoint returns a station's capacity, occupied and free slots and cars ready to rent. The telemetry worker now starts right after database migrations instead of waiting for the API. Added a system design document, an infrastructure specification with backup targets, two architecture decision records, a documentation maintenance regime and a CI check that blocks code changes without matching docs.

## 2026-11-07

### Add monitoring and automatic rollback — 18:55 UTC
**Summary:** The app now shows its own health on a dashboard and a faulty release rolls back by itself.
**Details:** Adds metrics and structured logs to the API, a Grafana dashboard, Prometheus, Loki and an error-rate alert, and a canary check that aborts a release when more than 5% of requests fail.
