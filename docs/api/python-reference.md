---
title: Довідник Python-модулів (docstrings)
owner: "@YakymivDanylo"
status: published
review_date: 2027-02-18
review_cycle_days: 90
tags: [api]
---

# Довідник Python-модулів — згенеровано з docstrings

Варіативний пункт ЛР№11 для API-проєкту: статичний довідник з docstring-коментарів рідної екосистеми Python.
Сторінка не містить ручного опису функцій — лише директиви `::: модуль`, які плагін `mkdocstrings` (аналог Sphinx
autodoc для MkDocs, статичний аналіз через griffe) розгортає з коду `src/` під час кожної збірки. Змінилася
сигнатура чи docstring — довідник оновиться в наступному деплої сам.

## Сервіс станцій

::: fleet_management.services.station_service

## Сервіс оренд

::: fleet_management.services.rental_service
    options:
      members: [calculate_cost, start_rental, end_rental, validate_rental_eligibility]

## Обробка телеметрії

::: fleet_management.telemetry.processor

Пов'язано: [[api-overview]] · [[sdd]] · #api
