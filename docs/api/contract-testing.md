---
title: Contract-тест і контроль дрейфу
owner: "@YakymivDanylo"
status: published
review_date: 2027-02-18
review_cycle_days: 90
tags: [api]
---

# Contract-тест: контракт проти живого коду

Контракт [`openapi.yaml`](openapi.yaml) — джерело істини, але код пишуть люди. Розбіжність між задокументованим
і фактичним форматом відповіді — **дефект документації або коду**, і її має знайти машина, а не користувач SDK.

## Як запускати

```powershell
# 1. Sandbox API (README); CORS — лише якщо потрібен Try it out з сайту документації
$env:CORS_ALLOW_ORIGINS = "http://127.0.0.1:8001"
docker compose -p fleet_sandbox --env-file .env.sandbox up -d --build
python scripts/seed_demo.py

# 2. Schemathesis: приклади, межові значення, фазинг і stateful-сценарії за контрактом
pip install schemathesis==4.33.4
st run docs/api/openapi.yaml --url http://localhost:8000 --checks all `
   --exclude-checks unsupported_method,allow_header_conformance --max-examples 100 --seed 42
```

Поріг: **0 failures**. `--checks all` перевіряє, серед іншого, що кожен код відповіді задокументований (ST103),
тіло відповідає схемі (ST108), немає 5xx (ST101), `Content-Type` збігається (ST105).

## Що знайшов тест (ЛР№11)

| # | Що побачив Schemathesis | Тип дефекту | Виправлення |
|---|---|---|---|
| 1 | `started_at`/`ended_at` = `2026-11-20T11:13:57.158655` — без часової зони, не RFC 3339 `date-time` | **код** розходився з контрактом | `RentalRead` віддає наївні UTC-мітки як `…Z` (`schemas.py`), тест `tests/unit/test_rental_schema.py` |
| 2 | 422 повертає `detail` масивом порушень, а контракт описував рядок | **контракт** не відповідав коду | `Error.detail` = рядок **або** масив `ValidationIssue` |
| 3 | Некоректний JSON у тілі → 400, а 400 не задокументовано | **контракт** | додано `400 BadRequest` для POST-операцій |
| 4 | `station_id`/`vehicle_id`/`rental_id` = 2 147 483 648 → **500** (OverflowError asyncpg, traceback у відповіді sandbox) | **код** | межі id `1..2^31−1` у шляхах і тілах → 422 (`DbId`, `PathId`), `tests/unit/test_id_bounds.py` |
| 5 | `POST /rentals/start` з неіснуючим `renter_id` → **500** (порушення FK) замість 404 | **код** | явна перевірка орендаря в `rental_service.start_rental`, integration-тест |
| 6 | `TRACE` → 405 без заголовка `Allow` (відповідає nginx, не FastAPI); `OPTIONS /stations` → `Allow: POST` | інфраструктура / фреймворк, поза контрактом | прийнято як відоме відхилення: TRACE відсікає nginx до проксування (репліка сама відповідає `405, Allow: POST`); методи поза контрактом виключено з перевірки |

Фінальний прогін: 1124 згенеровані кейси, усі 4 фази (Examples, Coverage, Fuzzing, Stateful) — ✅, 0 failures.
Сирі логи кожної ітерації — у [звіті ЛР№11](../lab11/REPORT.md).

## Чому довідка не може розійтися з контрактом

Сторінка [[openapi-reference|довідки]] містить лише `<swagger-ui src="openapi.yaml"/>`; під час збірки плагін
копіює контракт поруч і генерує iframe, у якому Swagger UI завантажує `../openapi.yaml`. Тобто в зібраному сайті
є **одна копія** контракту, і довідка — її рендер. Змінити версію або формат «лише в довідці» неможливо: такого
тексту немає. Перевірити: `mkdocs build` → `site/api/openapi.yaml` побайтово збігається з `docs/api/openapi.yaml`.

Пов'язано: [[api-overview]] · [[sdk]] · [[CONTRIBUTING#definition-of-done-docs-or-dont-merge|DoD]] · #api
