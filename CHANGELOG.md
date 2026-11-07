# Changelog

All notable changes to this project, newest first. Entries are grouped by UTC date.

## 2026-11-07

### Add monitoring and automatic rollback — 18:55 UTC
**Summary:** The app now shows its own health on a dashboard and a faulty release rolls back by itself.
**Details:** Adds metrics and structured logs to the API, a Grafana dashboard, Prometheus, Loki and an error-rate alert, and a canary check that aborts a release when more than 5% of requests fail.
