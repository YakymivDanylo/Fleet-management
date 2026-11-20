# Fleet Management System (Каршерінг)

[![Docs](https://github.com/YakymivDanylo/Fleet-management/actions/workflows/docs.yml/badge.svg)](https://github.com/YakymivDanylo/Fleet-management/actions/workflows/docs.yml)

**Що це.** Бекенд і вебінтерфейс **станційного каршерінгу** (Fleet Management з IoT-телеметрією, варіант №13):
компанія володіє парком авто, клієнти орендують їх на короткий термін, забираючи й повертаючи на фіксованих
станціях. Система веде станції, авто, орендарів і оренди, приймає безперервну телеметрію авто (координати,
пальне/заряд, замок), показує актуальний стан парку та доступність кожної станції; підтримує ролі `user`/`admin`
та вимоги GDPR (експорт, анонімізація, згоди).

**База знань (Documentation as Code):** <https://yakymivdanylo.github.io/Fleet-management/> — збирається з `docs/`
командою `mkdocs build --strict` і публікується конвеєром `.github/workflows/docs.yml`.

## Швидкий старт (5 хвилин)

Потрібно: Docker Desktop (Compose v2), Git.

```powershell
git clone https://github.com/YakymivDanylo/Fleet-management.git
cd Fleet-management
Copy-Item .env.sandbox.example .env.sandbox
python -c "import secrets; print(secrets.token_urlsafe(48))"   # вставте як JWT_SECRET_KEY у .env.sandbox
docker compose -p fleet_sandbox --env-file .env.sandbox up -d --build
```

Перевірка: `docker compose -p fleet_sandbox ps` — усі сервіси `healthy`; <http://localhost:8000/health> →
`{"status":"ok","db":"connected"}`; вебінтерфейс — <http://localhost:8000/app/>.

```powershell
docker compose -p fleet_sandbox --env-file .env.sandbox exec -it api1 create-admin --email admin@example.com
python scripts/seed_demo.py                                          # демо-дані
docker compose -p fleet_sandbox --env-file .env.sandbox down         # -v — видалити й дані БД
```

## Куди далі — піраміда документації

| Рівень | Питання | Розділ бази знань | Джерело в репозиторії |
|---|---|---|---|
| 1 · README | Що це і як запустити? | цей файл | `README.md` |
| 2 · Developer Docs | Як приєднатися до розробки? | [Developer Docs](https://yakymivdanylo.github.io/Fleet-management/developer/developer-index/) | [`docs/developer/`](docs/developer/) — [CONTRIBUTING](docs/developer/CONTRIBUTING.md), [локальне середовище й тести](docs/developer/local-setup.md), [стандарти коду](docs/developer/code-standards.md) |
| 3 · API Docs | Як інтегруватися? | [API Docs](https://yakymivdanylo.github.io/Fleet-management/api/api-overview/) | [`docs/api/openapi.yaml`](docs/api/openapi.yaml) — API-first контракт (SSOT) |
| 4 · Architecture Docs | Чому система влаштована саме так? | [Architecture Docs](https://yakymivdanylo.github.io/Fleet-management/architecture/architecture-index/) | [`docs/architecture/`](docs/architecture/) — [SDD](docs/architecture/sdd.md), [ISD](docs/architecture/isd.md), [ADR](docs/architecture/adr/index.md) |

Історія змін для всіх — [CHANGELOG.md](CHANGELOG.md).

## Definition of Done: документаційні перевірки

PR, що змінює публічну поведінку, не зливається без оновлення `docs/`, OpenAPI і CHANGELOG — чек-лист
«docs-or-don't-merge» у [CONTRIBUTING](docs/developer/CONTRIBUTING.md#definition-of-done-docs-or-dont-merge).
Автоматично перевіряється:

| Що | Інструмент | Стадія конвеєра | Поріг |
|---|---|---|---|
| Контракти API | Spectral (`.spectral.yaml`) | `Docs` → `api-contract` | 0 errors |
| Розмітка | markdownlint-cli2 (`.markdownlint-cli2.yaml`) | `Docs` → `lint` | 0 порушень |
| Посилання, навігація, якорі | `mkdocs build --strict` | `Docs` → `build` | 0 warnings, інакше Exit Code 1 |
| Актуальність | `review_date` з front matter (`scripts/docs_review_audit.py`) | `Docs` → `review-audit` | 0 прострочених живих сторінок |
| Відповідність коду і контракту | Schemathesis (`docs/api/contract-testing.md`) | локально / перед релізом | 0 failures |
| Дрейф коду й документації | `scripts/doc_audit.py --strict` | `CI` → `docs-currency` | усі маршрути в SDD, drift ≤ 20 комітів |
