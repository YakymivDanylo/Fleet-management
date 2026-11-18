#!/bin/sh
# Lab 8: start the application stack together with Prometheus + Grafana.
docker compose -p fleet_sandbox --env-file .env.sandbox -f docker-compose.yml -f docker-compose.monitoring.yml up -d --build
