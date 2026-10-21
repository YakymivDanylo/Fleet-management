# Звіт: Лабораторна робота №5 — Контейнеризація веб-системи за допомогою Docker

**Застосунок:** Fleet Management (каршерінг) — FastAPI API + telemetry worker, PostgreSQL, Redis, RabbitMQ
**Гілка:** `feat/lab4-lab5-loadtest-docker`
**Дата виконання:** 2026-10-17
**Середовище:** Docker Engine 29.8.0 (Docker Desktop, Windows 11), Compose v2

Усі команди виконано на реальному Docker; повний вивід кожного кроку — у каталозі [`outputs/`](outputs/).

| Крок | Підтвердження |
|---|---|
| Збірка й запуск однією командою `docker compose up --build` | [`01-compose-up-build.txt`](outputs/01-compose-up-build.txt) |
| Усі сервіси `healthy`, БД і Redis без опублікованих портів | [`02-compose-ps.txt`](outputs/02-compose-ps.txt) |
| Міграції Alembic виконано в контейнері, таблиці створено | [`03-migrations.txt`](outputs/03-migrations.txt) |
| API відповідає, запис і читання з БД працюють | [`04-api-check.txt`](outputs/04-api-check.txt) |
| Ізоляція мереж | [`05-networks.txt`](outputs/05-networks.txt) |
| Дані зберігаються після `docker compose down` | [`06-persistence.txt`](outputs/06-persistence.txt) |
| Multi-stage: розмір образу | [`07-image-size.txt`](outputs/07-image-size.txt) |
| Hot-reload через bind mount | [`08-hot-reload.txt`](outputs/08-hot-reload.txt) |

## 1. Dockerfile бекенду

[`Dockerfile`](../../Dockerfile) (API) і [`Dockerfile.worker`](../../Dockerfile.worker) (споживач телеметрії):

- **Базовий образ:** `python:3.13-slim` (Debian slim, без компіляторів). Обидва етапи на одному образі, тому скомпільовані колеса з першого етапу сумісні з другим.
- **Робоча директорія:** `WORKDIR /app`.
- **Команда запуску:** `alembic upgrade head && exec uvicorn fleet_management.main:app --host 0.0.0.0 --port 8000`. Міграції виконуються перед стартом сервера, а `exec` робить uvicorn процесом PID 1, щоб він отримував `SIGTERM` від `docker stop`.
- Процес запускається від непривілейованого `appuser`; `pip`/`setuptools` з фінального образу видалено.
- **[`.dockerignore`](../../.dockerignore)** не пускає в контекст збірки `.git`, `.env` і `.env.*` (окрім `*.example`), `__pycache__`, `*.pyc`, `*.log`/`logs`, `.venv`, кеші pytest/ruff, IDE-теки, а також усе, що не потрібне образу: `tests`, `docs`, `chart`, `k8s`, `loadtest`, `scripts`, compose-файли. Через це контекст збірки займає лише ~105 kB (`transferring context: 105.34kB` у [`01-compose-up-build.txt`](outputs/01-compose-up-build.txt)), а в `/app` контейнера лежать тільки `alembic/` і `alembic.ini` ([`07-image-size.txt`](outputs/07-image-size.txt)). Код встановлено пакетом у `/opt/venv`.

## 2. База даних в контейнері та Docker Volumes

- Офіційний образ `postgres:16`; користувач, пароль і назва БД беруться зі змінних оточення (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`).
- Каталог даних `/var/lib/postgresql/data` змонтовано в іменований том `pgdata`; RabbitMQ так само зберігає дані в `rabbitmq_data`.
- **Перевірка ([`06-persistence.txt`](outputs/06-persistence.txt)):** створено станцію й авто → `docker compose down` (контейнери й мережі видалено, томи `fleet_lab5_pgdata` / `fleet_lab5_rabbitmq_data` лишилися) → `docker compose up -d` → `GET /vehicles` повертає те саме авто `BC-5005-AA`. Дані зникнуть лише після явного `docker compose down -v`.
- Порт 5432 на хост не опубліковано: підключення з хоста завершується тайм-аутом, тобто БД доступна тільки з внутрішньої мережі.

## 3. Оркестрація через `docker-compose.yml`

[`docker-compose.yml`](../../docker-compose.yml) описує сервіси `db`, `redis`, `rabbitmq`, `api`, `worker`, а також `toxiproxy` (профіль `fault`) і `k6` (профіль `loadtest`).

**Змінні оточення з `.env`.** Compose автоматично читає `.env` з кореня проєкту й підставляє `${...}` у файл. Обов'язкові змінні записано як `${VAR:?пояснення}`: якщо змінна відсутня, compose зупиняється з повідомленням ще до запуску контейнерів, а не стартує з порожнім паролем. Шаблон з усіма змінними — у [`.env.example`](../../.env.example); `.env` додано в `.gitignore`. Для окремих середовищ лишився варіант `--env-file .env.sandbox` / `.env.production`.

**Мережі:**

| Мережа | Тип | Сервіси | Навіщо |
|---|---|---|---|
| `backend` | `internal: true` | db, redis, rabbitmq, api, worker, toxiproxy | Внутрішній обмін за іменами сервісів (`db:5432`, `redis:6379`); немає маршруту назовні й не можна опублікувати порт |
| `edge` | bridge | api, rabbitmq (UI 15672), toxiproxy (API 8474), k6 | Лише сервіси, порти яких мають бути доступні з хоста |

Перевірка ([`05-networks.txt`](outputs/05-networks.txt)): `api → db:5432` працює; `worker → 1.1.1.1:80` — `Network is unreachable`; `host → 5432` — тайм-аут.

**Порядок запуску (`depends_on` + `healthcheck`):**

```
db (pg_isready) ─┐
redis (redis-cli ping) ─┼─► api (GET /health → SELECT 1) ─┐
                 │                                        ├─► worker
rabbitmq (rabbitmq-diagnostics ping) ─────────────────────┘
```

`api` стартує лише коли `db` і `redis` у стані `healthy` (`condition: service_healthy`). Інакше `alembic upgrade head` упав би на ще не готовій БД. `worker` чекає на `healthy` api (тобто таблиці вже створено міграціями) і rabbitmq. Healthcheck самого api робить `SELECT 1` через `/health`, тому `healthy` означає «сервер працює і бачить БД». У [`01-compose-up-build.txt`](outputs/01-compose-up-build.txt) видно саме цю черговість: `db Healthy`, `redis Healthy` → `api Started` → `api Healthy`, `rabbitmq Healthy` → `worker Started`.

## 4. Перевірка та розгортання

- `docker compose up --build` без додаткових параметрів зібрав два образи й підняв усю систему за ~47 с ([`01-compose-up-build.txt`](outputs/01-compose-up-build.txt), [`02-compose-ps.txt`](outputs/02-compose-ps.txt)).
- У логах api видно 4 міграції Alembic (`initial schema` → `privacy engineering tables`), `alembic_version = c3a91f0b7d21` і 13 таблиць у БД ([`03-migrations.txt`](outputs/03-migrations.txt)).
- `GET /health` → `{"status":"ok","db":"connected"}`; `POST /stations`, `POST /vehicles`, `GET /vehicles` записують у БД і читають з неї ([`04-api-check.txt`](outputs/04-api-check.txt)).

## Додаткове завдання 1. Multi-stage build

Етап `builder` створює venv у `/opt/venv`, встановлює залежності з `requirements.txt` і сам пакет. Фінальний етап бере чистий `python:3.13-slim` і копіює лише `/opt/venv` та файли міграцій. Шари з кешем pip, вихідними файлами `src/` і `requirements.txt` до фінального образу не потрапляють.

Порівняння ([`07-image-size.txt`](outputs/07-image-size.txt)):

| Образ | Розмір | Примітка |
|---|---|---|
| Наївна одноетапна збірка на `python:3.13` ([`Dockerfile.single-stage`](Dockerfile.single-stage)) | **1.81 GB** | gcc, заголовки, pip, запуск від root |
| Етап `builder` (`--target builder`) | 325 MB | slim + pip + вихідні файли |
| **Фінальний multi-stage образ api** | **312 MB** | без pip/setuptools/gcc, `appuser` |

Розмір зменшився в ~5.8 раза відносно наївної збірки. У фінальному образі `which gcc` нічого не знаходить, `python -m pip` повертає `No module named pip`.

## Додаткове завдання 2. Режим розробки з hot-reload

Окремий файл [`docker-compose.dev.yml`](../../docker-compose.dev.yml) накладається поверх основного:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- **Bind mounts:** `./src → /app/src` і `./alembic → /app/alembic`.
- `PYTHONPATH=/app/src`: пакет в образі встановлено в site-packages, а каталоги з `PYTHONPATH` мають пріоритет, тому імпортується змонтований з хоста код.
- Команда запуску з `--reload --reload-dir /app/src`.
- `WATCHFILES_FORCE_POLLING=true`: Docker Desktop на Windows не передає події inotify з файлів хоста в bind mount, тому без опитування reloader змін не помітить.

Перевірка ([`08-hot-reload.txt`](outputs/08-hot-reload.txt)): у `/info` на хості додано поле `hot_reload`. Через кілька секунд лог показав `WatchFiles detected changes in 'src/fleet_management/main.py'. Reloading...`, і відповідь `/info` уже містила нове поле. Контейнер не перезбирався й не перестворювався (той самий `pod`). Продакшн-запуск (`docker compose up`) цього файлу не використовує й працює з незмінним кодом з образу.
