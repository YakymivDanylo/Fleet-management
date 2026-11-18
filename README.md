# Fleet Management System (Каршерінг)

**Що це і для кого.** Бекенд і вебінтерфейс **станційного каршерінгу** (Fleet Management з IoT-телеметрією,
варіант №13): компанія володіє парком авто, клієнти орендують їх на короткий термін, забираючи й повертаючи
на фіксованих станціях. Система веде станції, авто, орендарів і оренди, приймає безперервну телеметрію авто
(координати, пальне/заряд, замок) і показує актуальний стан парку та **доступність кожної станції** (вільні місця
для повернення і вільні авто — `GET /stations/{station_id}/availability`); підтримує ролі `user`/`admin` та вимоги
GDPR (експорт, анонімізація, згоди).

| Аудиторія | Почніть з |
|---|---|
| Бізнес / замовник | цей розділ і [«Предметна область»](#предметна-область) |
| Новачок-розробник | [Швидкий старт](#швидкий-старт-5-хвилин) → [Шлях онбордингу](#шлях-онбордингу) |
| Розробник | [«Архітектура коротко»](#архітектура-коротко), код `src/fleet_management/` (`api/ → services/ → models/`) |
| QA | `/docs` (OpenAPI), `tests/integration/test_api.py` |
| DevOps | [«Середовища»](#середовища-sandbox-і-production), [Helm-чарт](charts/fleet-management/README.md), `.github/workflows/ci.yml` |

## Швидкий старт (5 хвилин)

Потрібно: Docker Desktop (Compose v2), Git. Python 3.13 — лише для тестів поза контейнерами.

```powershell
git clone https://github.com/YakymivDanylo/Fleet-management.git
cd Fleet-management
Copy-Item .env.sandbox.example .env.sandbox
python -c "import secrets; print(secrets.token_urlsafe(48))"   # вставте як JWT_SECRET_KEY у .env.sandbox
docker compose -p fleet_sandbox --env-file .env.sandbox up -d --build
```

Перевірка: `docker compose -p fleet_sandbox ps` — усі сервіси `healthy`; http://localhost:8000/health →
`{"status":"ok","db":"connected"}`; вебінтерфейс — http://localhost:8000/app/, OpenAPI — http://localhost:8000/docs.

Перший адміністратор і зупинка:

```powershell
docker compose -p fleet_sandbox --env-file .env.sandbox exec -it api1 create-admin --email admin@example.com
docker compose -p fleet_sandbox --env-file .env.sandbox down        # додайте -v, щоб видалити дані БД
```

Міграції (`alembic upgrade head`) виконує одноразовий сервіс `migrate` до старту реплік API.

## Шлях онбордингу

1. **README** (цей файл) — призначення, швидкий старт, запуск тестів.
2. **OpenAPI** (`/docs` після запуску) — усі HTTP-контракти.
3. **[Helm-чарт](charts/fleet-management/README.md)** — розгортання в Kubernetes.
4. **`.github/workflows/ci.yml`** — CI/CD-гейти; правило: «зміна коду = зміна документації» (PR-шаблон).

## Предметна область

### Ключові сутності

- **Vehicle** — автомобіль парку: держномер, модель, статус (available / rented / maintenance), поточна станція.
- **Station** — фіксована станція видачі/повернення: адреса, місткість; доступність (зайняті й вільні місця,
  авто, готові до оренди) обчислюється на льоту.
- **Renter** — клієнт, що орендує авто: ім'я, номер посвідчення, прив'язка до облікового запису.
- **Rental** — оренда: клієнт, авто, станція старту та фінішу, час початку/кінця, статус, вартість.
- **TelemetryReading** — показник телеметрії авто: координати, рівень пального/заряду, статус замка, часова мітка.

### Сценарій навантаження

1. **Безперервний потік телеметрії** йде через **RabbitMQ** (черга `telemetry`) до окремого worker'а, щоб
   пікові записи не блокували API; останній стан авто кешується в **Redis**.
2. **Конкурентний доступ:** у пікові години кілька клієнтів можуть одночасно бронювати останнє авто на станції.
   Зараз старт оренди перевіряє статус авто без блокування рядка (`SELECT … FOR UPDATE` не застосовується) —
   це відоме обмеження.

## Архітектура коротко

Браузер (SPA `/app`) → **nginx** → 3 репліки **FastAPI** → PostgreSQL / Redis; IoT-модулі авто → **RabbitMQ** →
**telemetry-worker** → PostgreSQL / Redis.

## Середовища sandbox і production

Застосунок має два оточення, які задаються змінною `APP_ENV` (`sandbox` або `production`). Налаштування беруться
зі змінних оточення / файлу `.env.<APP_ENV>`; у коді та `docker-compose.yml` секретів немає. Кожне оточення має
власну БД, контейнери, томи й порти. Застосунок не стартує, якщо ім'я БД не відповідає оточенню, а у production —
якщо `DEBUG=true` або `JWT_SECRET_KEY` коротший за 32 символи.

| | sandbox | production |
|---|---|---|
| Файл конфігурації | `.env.sandbox` | `.env.production` |
| `DEBUG` | дозволено `true` | завжди `false` (інакше помилка старту) |
| БД | `fleet_sandbox` | `fleet_production` |
| API | http://localhost:8000 | http://localhost:8080 |
| `/docs`, `/redoc`, `/openapi.json` | доступні | вимкнені (404) |
| Помилка 500 | `{"detail":"Internal server error","request_id":"…"}`, traceback лише в логах | те саме |

```powershell
Copy-Item .env.production.example .env.production   # заповніть JWT_SECRET_KEY, POSTGRES_PASSWORD, RABBITMQ_DEFAULT_PASS
docker compose -p fleet_production --env-file .env.production up -d --build   # можна одночасно зі sandbox
```

Режим розробки з hot reload: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`.
Kubernetes (Helm, Argo CD, canary-релізи) — у [README чарта](charts/fleet-management/README.md).

## Тести та лінтер

```powershell
docker run -d --name test-pg -e POSTGRES_USER=test_user -e POSTGRES_PASSWORD=test_pass -e POSTGRES_DB=fleet_management_test -p 55432:5432 postgres:16
docker run -d --name test-redis -p 56379:6379 redis:7-alpine
$env:TEST_DATABASE_URL = "postgresql+asyncpg://test_user:test_pass@localhost:55432/fleet_management_test"
$env:TEST_REDIS_URL = "redis://localhost:56379/15"
pytest tests -v
ruff check . ; ruff format --check .
```

CI (GitHub Actions) запускає лінтер, тести, гейти складності, coverage + mutation score, SCA, gitleaks,
SonarCloud і Trivy на кожен pull request і push у `main` (`.github/workflows/ci.yml`).

## Додаткові інструменти

| Задача | Команда |
|---|---|
| Розподіл запитів по репліках | `python scripts/lb_check.py -n 15` (поле `pod` у `GET /info`) |
| Алгоритм балансування | `NGINX_CONF=./nginx/least_conn.conf docker compose up -d --force-recreate nginx` |
| Навантажувальний тест k6 | `docker compose run --rm --no-deps k6 run /scripts/user_journey.js` (сценарій `loadtest/user_journey.js`) |
| Збій Redis (toxiproxy) | `docker compose --profile fault up -d toxiproxy`, `python scripts/fault.py` |
| Аудит актуальності документації | `python scripts/doc_audit.py --strict` |

## Документація

| Документ | Тип | Аудиторія |
|---|---|---|
| [charts/fleet-management/README.md](charts/fleet-management/README.md) | продукт, експлуатаційна | DevOps |
| [CHANGELOG.md](CHANGELOG.md) | процес (історія змін) | бізнес, усі |
| [k8s/README.md](k8s/README.md) | deprecated | — |
