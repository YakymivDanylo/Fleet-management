---
title: Локальне середовище розробника
owner: "@YakymivDanylo"
status: published
review_date: 2027-02-18
review_cycle_days: 90
tags: [ops]
---

# Локальне середовище розробника

Запуск усього стеку в Docker — у README (рівень 1). Тут — те, що потрібно для **розробки**: тести, лінтери,
pre-commit і збірка бази знань. Топологія контейнерів і змінні оточення — у [[isd|ISD]].

## Інструменти

| Інструмент | Версія | Навіщо |
|---|---|---|
| Docker Desktop (Compose v2) | ≥ 4.x | стек і тимчасові БД для тестів |
| Python | 3.13 | тести, скрипти, MkDocs |
| Node.js | ≥ 20 | markdownlint-cli2, Spectral (через `npx`) |
| Git | ≥ 2.40 | історія = дати редагування сторінок (`git-revision-date-localized`) |

## Python-оточення та pre-commit

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install --no-deps -e .
pre-commit install          # ruff, ruff-format, gitleaks, BOM/LF, check-ast, complexity-gate
```

## Тести

Integration-тести потребують окремих PostgreSQL і Redis (БД `fleet_management_test`, Redis db 15):

```powershell
docker run -d --name test-pg -e POSTGRES_USER=test_user -e POSTGRES_PASSWORD=test_pass -e POSTGRES_DB=fleet_management_test -p 55432:5432 postgres:16
docker run -d --name test-redis -p 56379:6379 redis:7-alpine
$env:TEST_DATABASE_URL = "postgresql+asyncpg://test_user:test_pass@localhost:55432/fleet_management_test"
$env:TEST_REDIS_URL = "redis://localhost:56379/15"
pytest tests -v
ruff check . ; ruff format --check .
```

## База знань (MkDocs)

```powershell
pip install -r requirements-docs.txt
mkdocs serve -a 127.0.0.1:8001          # live reload
mkdocs build --strict                   # те саме, що стадія build у CI: будь-яке попередження = Exit Code 1
npx markdownlint-cli2@0.24.2 "docs/**/*.md" "README.md"
npx @stoplight/spectral-cli@6.17.1 lint docs/api/openapi.yaml
python scripts/docs_review_audit.py     # прострочені review_date
python scripts/kb_graph.py              # зв'язність графа знань (як у Obsidian)
```

Obsidian: «Open folder as vault» → корінь репозиторію. Налаштування `.obsidian/app.json` виключає зі
сховища службові каталоги, тож граф показує лише базу знань. Посилання між документами пишемо як
`[[sdd]]`, `[[isd#isd-backup|ISD §7]]` — хук `docs_hooks/wikilinks.py` перетворює їх на звичайні посилання
сайту, а неіснуюча ціль ламає strict-збірку.

## Додаткові інструменти

| Задача | Команда |
|---|---|
| Розподіл запитів по репліках | `python scripts/lb_check.py -n 15` (поле `pod` у `GET /info`) |
| Алгоритм балансування | `NGINX_CONF=./nginx/least_conn.conf docker compose up -d --force-recreate nginx` |
| Навантажувальний тест k6 | `docker compose run --rm --no-deps k6 run /scripts/user_journey.js` |
| Збій Redis (toxiproxy) | `docker compose --profile fault up -d toxiproxy`, `python scripts/fault.py` |
| Режим hot reload | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build` |
| Аудит актуальності документації (ЛР№10) | `python scripts/doc_audit.py --strict` |

Пов'язано: [[CONTRIBUTING]] · [[code-standards]] · [[sdd]] · #ops
