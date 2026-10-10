# ЛР №3 (Web): sandbox / production, змінні оточення, CI/CD

Інструкція із запуску та демонстрації. Усі команди — для PowerShell з кореня репозиторію.

## 1. Що реалізовано

| Вимога | Реалізація |
|---|---|
| Конфігурація без hardcode | `src/fleet_management/config.py` (pydantic-settings) читає `.env.<APP_ENV>`; у коді та `docker-compose.yml` немає жодного пароля чи ключа |
| Файли оточень | шаблони `.env.sandbox.example`, `.env.production.example` (у git), реальні `.env.sandbox`, `.env.production` (у `.gitignore`) |
| Ізоляція БД | окремі БД `fleet_sandbox` / `fleet_production`, окремі compose-проєкти (контейнери, мережа, томи, порти) |
| Захист від плутанини | `Settings` не створюється, якщо ім'я БД не відповідає оточенню (production ↔ `*_production`, sandbox ↔ `*_sandbox`/`*_test`); alembic і `create-admin` теж проходять цю перевірку |
| `DEBUG=False` у production | валідатор: `APP_ENV=production` + `DEBUG=true` → застосунок не стартує; FastAPI створюється з `debug=settings.debug` |
| Безпечні 500 | глобальний обробник: клієнту `{"detail":"Internal server error","request_id":"…"}`, traceback — лише у лог сервера з тим самим `request_id` |
| Додатково (production) | `/docs`, `/redoc`, `/openapi.json` вимкнені; потрібен `JWT_SECRET_KEY` ≥ 32 символів; Toxiproxy у production не запускається |
| CI/CD (варіант A) | `.github/workflows/ci.yml`: на кожен PR у `main` і push у `main` — ruff (check + format) та весь `pytest tests` |

## 2. Підготовка

```powershell
Copy-Item .env.sandbox.example .env.sandbox
Copy-Item .env.production.example .env.production

# Згенерувати секрет (окремий для кожного оточення!) і вписати в JWT_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Відкрити обидва файли й заповнити порожні поля (`JWT_SECRET_KEY`, у production ще `POSTGRES_PASSWORD`, `RABBITMQ_DEFAULT_PASS`). Для паролів використовуйте символи без `@ : / ? #`, бо з них складається URL підключення. Значення у `.env.*` — тестові, реальні дані до репозиторію не потрапляють.

Якщо обов'язкова змінна порожня, `docker compose` зупиняється з повідомленням, що саме треба заповнити.

## 3. Запуск sandbox

```powershell
docker compose -p fleet_sandbox --env-file .env.sandbox up -d --build
docker compose -p fleet_sandbox --env-file .env.sandbox ps
```

- API: http://localhost:8000 (Swagger: http://localhost:8000/docs)
- Образ при старті сам виконує `alembic upgrade head`.
- `COMPOSE_PROFILES=fault` у `.env.sandbox` додатково піднімає Toxiproxy (fault-injection з ЛР №2).
- Перший адміністратор:

```powershell
docker compose -p fleet_sandbox --env-file .env.sandbox exec -it api create-admin --email admin@example.com
```

Зупинка (з видаленням даних sandbox): `docker compose -p fleet_sandbox --env-file .env.sandbox down -v`.

## 4. Запуск production

```powershell
docker compose -p fleet_production --env-file .env.production up -d --build
docker compose -p fleet_production --env-file .env.production ps
```

- API: http://localhost:8080 (порт задається `API_PORT`), `/docs` повертає 404.
- Sandbox і production можна тримати запущеними одночасно: різні імена проєктів, томи й порти.
- Перший адміністратор — так само, але з `-p fleet_production --env-file .env.production`.

## 5. Перевірка ізоляції баз даних

Створити запис у sandbox і переконатися, що в production його немає:

```powershell
curl.exe -s -X POST http://localhost:8000/stations -H "Content-Type: application/json" -d '{\"address\":\"Sandbox st\",\"capacity\":3}'
curl.exe -s http://localhost:8000/stations   # є запис
curl.exe -s http://localhost:8080/stations   # []
```

Те саме напряму в PostgreSQL (імена користувачів/БД — з ваших `.env.*`):

```powershell
docker exec fleet_sandbox-db-1    psql -U fleet_sandbox_user    -d fleet_sandbox    -c "SELECT count(*) FROM stations;"   # 1
docker exec fleet_production-db-1 psql -U fleet_production_user -d fleet_production -c "SELECT count(*) FROM stations;"   # 0
docker exec fleet_production-db-1 psql -U fleet_production_user -d fleet_production -c "\l"                                # у production-сервері немає fleet_sandbox
```

Захист від помилки конфігурації — production, спрямований на sandbox-БД, не стартує:

```powershell
docker run --rm -e APP_ENV=production -e DATABASE_URL=postgresql+asyncpg://u:p@h/fleet_sandbox -e JWT_SECRET_KEY=$("s" * 40) fleet_production-api python -c "import fleet_management.config"
# ValidationError: APP_ENV=production requires a database name ending with _production, got 'fleet_sandbox'
```

## 6. Перевірка DEBUG=False та поведінки помилки 500

```powershell
docker exec fleet_production-api-1 env | Select-String "APP_ENV|DEBUG"     # APP_ENV=production, DEBUG=false
curl.exe -s -o NUL -w "%{http_code}\n" http://localhost:8080/docs          # 404
curl.exe -s -o NUL -w "%{http_code}\n" http://localhost:8080/openapi.json  # 404
```

`DEBUG=true` у production заборонено:

```powershell
docker run --rm -e APP_ENV=production -e DEBUG=true -e DATABASE_URL=postgresql+asyncpg://u:p@h/fleet_production -e JWT_SECRET_KEY=$("s" * 40) fleet_production-api python -c "import fleet_management.config"
# ValidationError: DEBUG must be false when APP_ENV=production
```

Справжня помилка 500: зупинити БД production і викликати `/health`.

```powershell
docker stop fleet_production-db-1
curl.exe -i http://localhost:8080/health
# HTTP/1.1 500 Internal Server Error
# {"detail":"Internal server error","request_id":"a62f7d8917a845ad8e6b6a3bb8bd8d8e"}

docker logs --tail 20 fleet_production-api-1     # повний traceback — тут, з тим самим request_id
docker start fleet_production-db-1
```

Клієнт не бачить ні стектрейсу, ні імен файлів, ні тексту SQL-помилки.

## 7. Лінтер і тести локально

Тести потребують PostgreSQL і Redis (тимчасові контейнери; БД для тестів має суфікс `_test`, дозволений лише для sandbox):

```powershell
docker run -d --name test-pg -e POSTGRES_USER=test_user -e POSTGRES_PASSWORD=test_pass -e POSTGRES_DB=fleet_management_test -p 55432:5432 postgres:16
docker run -d --name test-redis -p 56379:6379 redis:7-alpine

$env:TEST_DATABASE_URL = "postgresql+asyncpg://test_user:test_pass@localhost:55432/fleet_management_test"
$env:TEST_REDIS_URL    = "redis://localhost:56379/15"
pip install -r requirements-dev.txt
pip install --no-deps -e .
pytest tests -v

docker rm -f test-pg test-redis
```

`tests/conftest.py` завжди примусово ставить `APP_ENV=sandbox`, тож змінні вашої оболонки тестам не заважають. Нові тести: `tests/unit/test_config.py` (завантаження за оточенням, валідатори DEBUG/секрету/імені БД) і `tests/unit/test_error_handling.py` (500 без traceback, вимкнені `/docs` у production).

Лінтер (локальний `ruff.exe` у `.venv` може бути зламаний, тому через Docker):

```powershell
docker run --rm -v "${PWD}:/io" -w /io ghcr.io/astral-sh/ruff:0.16.6 check .
docker run --rm -v "${PWD}:/io" -w /io ghcr.io/astral-sh/ruff:0.16.6 format --check .
```

## 8. Як працює CI/CD

Файл `.github/workflows/ci.yml`, запускається **на кожен pull request у `main` і на кожен push у `main`**:

1. `lint` — `ruff check .` та `ruff format --check .`.
2. `test` (matrix `api` / `worker`) — з сервісами Postgres і Redis виконує `pytest`: `api`-гілка запускає весь `tests/` крім тестів воркера, `worker`-гілка — тести воркера; разом це повний `pytest tests`. Змінні `APP_ENV=sandbox`, `DEBUG=false` задані на рівні job. Звіти покриття завантажуються як артефакти.
3. `complexity`, `sca`, `secrets`, `sonarcloud` — додаткові перевірки якості/безпеки (з попередніх ЛР).
4. `build` (потребує успіху всіх попередніх) — збірка Docker-образів + сканування Trivy.
5. `publish` — лише для push у `main`: публікація образів у GHCR.

Секрети у CI не зберігаються в коді: `SONAR_TOKEN` береться з GitHub Secrets, пароль тестової БД — одноразовий, потрібен лише service-контейнеру job.

Перевірка: створити PR у `main` → у вкладці Checks з'являються `Lint(ruff)` та `Build & Test (api|worker)`; зламаний форматування або тест робить PR червоним.
