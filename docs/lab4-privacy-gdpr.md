# Лабораторна робота №4 — Privacy Engineering та GDPR

Проєкт: Fleet Management (станційний каршерінг), FastAPI + PostgreSQL + Redis + RabbitMQ.
Усі дані в документі, тестах і демо — **синтетичні** (`alice.synthetic@example.com`,
`+380000000012`, штучні токени). Реальних ПД, паролів і токенів немає.

> Код цієї лабораторної: `src/fleet_management/privacy/` (логування), `services/{export,erasure,consent,marketing,audit}_service.py`,
> `api/privacy.py`, `models/privacy.py`, міграція `alembic/versions/c3a91f0b7d21_add_privacy_engineering.py`.
> Тести: `tests/unit/test_privacy_logging.py`, `tests/integration/test_privacy_{export,erasure,consent}.py`.

---

## 0. Запуск

### 0.1 Застосунок (Docker Compose)

```powershell
# .env у корені (не комітиться) має містити JWT_SECRET_KEY:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
docker compose up -d --build db redis toxiproxy api
docker compose logs api | Select-String "alembic"      # міграція c3a91f0b7d21 застосовується при старті api
```

API: <http://localhost:8000>, Swagger: <http://localhost:8000/docs> (кнопка **Authorize** для Bearer-токена).
Формат логів: `LOG_FORMAT=text` (за замовчуванням) або `LOG_FORMAT=json` (змінна середовища сервісу `api`).

SQL до БД для демо:

```powershell
docker compose exec db psql -U fleet_user -d fleet_management
```

### 0.2 Тести

Потрібні тимчасові Postgres і Redis (порти змінені, щоб не конфліктувати з compose):

```powershell
docker run -d --name lab4-pg -e POSTGRES_USER=fleet_user -e POSTGRES_PASSWORD=fleet_password `
  -e POSTGRES_DB=fleet_management_test -p 55433:5432 postgres:16
docker run -d --name lab4-redis -p 56380:6379 redis:7-alpine

$env:TEST_DATABASE_URL = "postgresql+asyncpg://fleet_user:fleet_password@localhost:55433/fleet_management_test"
$env:TEST_REDIS_URL    = "redis://localhost:56380/15"
pytest tests/unit/test_privacy_logging.py tests/integration/test_privacy_export.py `
       tests/integration/test_privacy_erasure.py tests/integration/test_privacy_consent.py -v
pytest tests            # весь набір (1315 тестів)

docker rm -f lab4-pg lab4-redis
```

Ті самі файли додано до job `Build & Test (api)` у `.github/workflows/ci.yml`.

---

## 1. Характеристика системи та PII inventory

**Стек:** FastAPI (async), SQLAlchemy 2 + asyncpg, PostgreSQL 16, Redis, RabbitMQ (телеметрія).
**Автентифікація:** JWT Bearer (PyJWT) + Argon2id (pwdlib); роль перечитується з БД на кожен запит
(`src/fleet_management/auth.py`). Токен анонімізованого користувача відхиляється (`is_active = false`).

### 1.1 Інвентаризація персональних даних

| Категорія | Поля | Джерело | Сховище | Зв'язки | У логах | В експорті |
|---|---|---|---|---|---|---|
| Прямі ідентифікатори | `email`, `full_name` | `POST /auth/register` | `users` | 1:1 `renters.user_id` | маскуються (`a***@…`, `A***`) | так (`profile`) |
| Контактні дані | `phone` | `POST /auth/register` | `users.phone` | — | маскується (`+***12`) | так (`profile`) |
| Дані профілю орендаря | `renters.full_name`, `license_number` | `POST /api/users/{id}/renter-profile` | `renters` | `users`, `rentals` | маскуються | так (`renter_profile`) |
| Технічні ідентифікатори | `ip_address`, `user_agent` | `POST /auth/login` | `user_activity` | `users` | не логуються | так (`activity`) |
| Історія дій | `action`, `occurred_at` | login та ін. | `user_activity` | `users` | лише факт події | так (`activity`) |
| Транзакційні записи | оренди: авто, станції, час, статус | `POST /rentals/start` | `rentals` (через `renters`) | `renters`, `vehicles`, `stations` | лише id | так (`rentals`) |
| Дані про згоду | purpose, статус, `policy_version`, `source`, час | `/api/users/{id}/consents/…` | `user_consents`, `consent_history` | `users` | лише id/результат | так (`consents`) |
| Результати залежних дій | маркетингові листи, події аналітики | gated-ендпоїнти | `marketing_messages`, `analytics_events` | `users` | лише id | так |
| Audit | `event_type`, actor/subject **id**, result, correlation id | усі privacy-операції | `audit_events` | без FK | так (безпечно) | **ні** (omission) |
| Телеметрія авто | координати, пальне, замок | RabbitMQ worker | `telemetry_readings` | `vehicles` (не `users`) | — | **ні** (omission) |

### 1.2 Поля, що ніколи не повертаються в експорті

`users.hashed_password`, будь-які access/refresh/reset/verification токени, `JWT_SECRET_KEY` та інші секрети,
внутрішні прапорці безпеки, дані **інших** користувачів. Контракт відповіді — явні pydantic-моделі
(`src/fleet_management/schemas_privacy.py`): поле, якого немає в моделі, у відповідь потрапити не може.

### 1.3 Контрольні тестові дані

`ALICE` / `BOB` у `tests/integration/privacy_support.py`: `alice.synthetic@example.com`, `Alice Synthetic`,
`+380000000012`, `SYN-LIC-ALICE-0001`. За ними перевіряються повнота експорту, маскування та відсутність PII
після анонімізації (скан **усіх** текстових колонок усіх таблиць).

---

## 2. Secure Logging (Завдання 1)

### 2.1 Політика логування

| Дані | Клас | Обробка |
|---|---|---|
| Correlation ID, id користувача (`user:42`), операція, статус, тривалість, рівень, час | **Дозволено** | без змін |
| Email | **Маскується** | `alice.synthetic@example.com` → `a***@example.com` |
| Телефон | **Маскується** | `+380000000012` → `+***12` |
| `full_name`, `license_number` (у структурах/`repr` DTO) | **Маскується** | `Alice Synthetic` → `A***` |
| password, hashed_password, access/refresh token, API key, secret, `Authorization`, JWT, Argon2-хеш | **Заборонено** | повністю `[REDACTED]` |
| Тіло запиту/відповіді, query string | **Заборонено** | не читається і не логується взагалі |

### 2.2 Централізований механізм

* `privacy/sanitizer.py` — чисті функції `sanitize_text` / `sanitize_value` (рекурсивно: dict, list, pydantic DTO, dataclass).
* `privacy/logging_setup.py` — `PiiSanitizingFilter` + `SanitizingFormatter` / `JsonSanitizingFormatter`.
  Фільтр обробляє `record.msg`, `record.args` (у т.ч. dict/DTO-аргументи), `extra=…`, `exc_info` (текст винятку
  й traceback), `stack_info`. `configure_logging()` ставить їх на всі handlers root-логера при старті
  (`main.py`, `telemetry/worker.py`) — окремі `logger.*`-виклики нічого не мають «пам'ятати».
* `privacy/middleware.py` — `CorrelationIdMiddleware`: `X-Correlation-ID` (вхід перевіряється regex-ом, інакше генерується)
  у contextvar і заголовок відповіді + **один безпечний access-лог** (метод, шлях без query, статус, тривалість).
  Тіла запитів/відповідей не читаються. Access-лог uvicorn вимкнено на користь цього.
* Формат не ламається: `correlation_id`, `operation`, рівень, час залишаються; JSON-лог — валідний JSON на кожен рядок.

### 2.3 Демо (крок 1) і приклад «до / після»

```powershell
$env:PYTHONPATH = "src"; $env:DATABASE_URL = "postgresql+asyncpg://x:y@localhost/z"
python scripts/privacy_log_demo.py
# LOG_FORMAT=json  — те саме у структурованому вигляді
```

Реальний вивід (той самий набір викликів):

```text
===== BEFORE (no sanitizer) =====
INFO register email=alice.synthetic@example.com phone=+380000000012 password=S3cret-Passw0rd-Synthetic  # gitleaks:allow
INFO payload={'user': {'email': 'alice.synthetic@example.com', 'full_name': 'Alice Synthetic'}, 'token': 'tok_synthetic_0123456789abcdef'}  # gitleaks:allow
WARNING request failed, header Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c3ludGhldGljLXNpZw
ERROR delivery failed
ValueError: cannot send to alice.synthetic@example.com (+380000000012) api_key=tok_synthetic_0123456789abcdef  # gitleaks:allow
-> leaked sensitive values: 5

===== AFTER (central sanitizer) =====
… INFO demo.True [demo-corr-0001]: register email=a***@example.com phone=+***12 password=[REDACTED]
… INFO demo.True [demo-corr-0001]: payload={'user': {'email': 'a***@example.com', 'full_name': 'A***'}, 'token': '[REDACTED]'}
… WARNING demo.True [demo-corr-0001]: request failed, header Authorization: [REDACTED]
… ERROR demo.True [demo-corr-0001]: delivery failed
ValueError: cannot send to a***@example.com (+***12) api_key=[REDACTED]
-> leaked sensitive values: 0
```

Реальний лог живого сервера під час усього демо (операції export / anonymize / consent) — жодного PII, лише id, результат і correlation id:

```text
… INFO fleet_management.audit [efc02416…]: audit event=marketing_email_action actor=user:2 subject=user:2 result=DENY:no_consent_on_record
… INFO fleet_management.access [efc02416…]: http_request method=POST path=/api/users/2/marketing-email status=403 duration_ms=14.9
```

`grep -ciE "alice|bob|synthetic|380000|passw|eyJ" server.log` → `0` (36 рядків логу).

### 2.4 Тести (`tests/unit/test_privacy_logging.py`, 13 тестів)

Позитивні: текст з `%`-аргументами; f-string з Bearer/JWT; **вкладений DTO** (pydantic, dict, dataclass); `repr` DTO у рядку;
**exception message + traceback**; `extra=`; JSON-лог (валідний, зберігає `correlation_id`); JSON усередині повідомлення;
формат/`correlation_id`/операція не руйнуються; числа й дати не псуються.
Негативний: `test_negative_control_unprotected_logger_does_leak` — той самий виклик **без** санітайзера має провалити
детектор витоку (`assert_no_leak`), тобто тест справді падає, якщо хоч одне вихідне значення потрапило в лог.

```text
tests/unit/test_privacy_logging.py::test_plain_text_masks_pii_and_redacts_secrets PASSED
tests/unit/test_privacy_logging.py::test_nested_dto_in_args_is_sanitized PASSED
tests/unit/test_privacy_logging.py::test_exception_message_and_traceback_are_sanitized PASSED
tests/unit/test_privacy_logging.py::test_json_log_stays_valid_and_keeps_diagnostics PASSED
tests/unit/test_privacy_logging.py::test_negative_control_unprotected_logger_does_leak PASSED
… (13 passed)
```

**Обмеження (чесно):** імена у вільному тексті без ключа (`"Alice Synthetic зателефонувала"`) regex не знайде — маскуються лише
структуровані `full_name=`/`license_number=` та ключі dict/DTO. Тому політика додатково забороняє логувати payload.

---

## 3. Personal Data Export (Завдання 2)

### 3.1 Контракт

`GET /api/users/{id}/personal-data` → `200 application/json`. Доступ: **сам суб'єкт** або **admin** (явне повноваження).
Для чужого id і для неіснуючого id — **однакова** відповідь `404 {"detail":"User not found"}` (без тіла з даними,
без розкриття існування чужого профілю). Без токена — `401`. Рішення про 404 замість 403 — свідоме (захист від перебору id / IDOR).

Секції та їх джерела:

| Секція | Джерело (таблиця) | Примітка |
|---|---|---|
| `profile` | `users` | id, email, full_name, phone, created_at |
| `settings` | `users` | role, is_active, anonymized |
| `renter_profile` | `renters` (`user_id`) | `null`, якщо профілю немає |
| `activity` | `user_activity` | дії + IP/user-agent |
| `rentals` | `rentals` через `renters` | лише власні оренди |
| `consents.current` / `.history` | `user_consents` / `consent_history` | policy_version, source, timestamps |
| `marketing_messages`, `analytics_events` | відповідні таблиці | результат gated-дій |
| `omissions` | константа | задокументовані пропуски: `credentials`, `telemetry`, `audit_events` |

Стабільність: `schema_version: "1.0"`, `generated_at` — UTC з суфіксом `Z`, усі часові поля UTC (`…Z`);
відсутні категорії — `[]` або `null` (передбачувана структура, не тихий пропуск).
Кожен експорт пишеться в `audit_events` (actor, subject, результат `ok`/`denied`, correlation id) — без PII.

### 3.2 Приклад відповіді (реальний, живий запит; скорочено `…`)

```json
{
    "schema_version": "1.0",
    "generated_at": "2026-10-10T07:33:02.652Z",
    "subject_id": 1,
    "data_categories": ["profile", "settings", "renter_profile", "activity", "rentals", "consents", "marketing_messages", "analytics_events"],
    "profile": {"id": 1, "email": "alice.synthetic@example.com", "full_name": "Alice Synthetic",
                "phone": "+380000000012", "created_at": "2026-10-10T07:32:54.987556Z"},
    "settings": {"role": "user", "is_active": true, "anonymized": false},
    "renter_profile": {"id": 1, "full_name": "Alice Synthetic", "license_number": "SYN-LIC-ALICE-0001"},
    "activity": [{"action": "login", "occurred_at": "2026-10-10T07:32:55.636684Z",
                  "ip_address": "127.0.0.1", "user_agent": "python-httpx"}],
    "rentals": [{"id": 1, "vehicle_id": 1, "start_station_id": 1, "end_station_id": null,
                 "started_at": "2026-10-10T07:32:57.153443Z", "ended_at": null, "status": "active"}],
    "consents": {
        "current": [{"purpose": "MARKETING_EMAIL", "status": "GRANTED", "policy_version": "2026-01",
                     "granted_at": "2026-10-10T07:32:57.440981Z", "withdrawn_at": null,
                     "updated_at": "2026-10-10T07:32:57.440981Z", "source": "web"}, …],
        "history": [{"purpose": "MARKETING_EMAIL", "action": "GRANT", "policy_version": "2026-01",
                     "source": "web", "occurred_at": "2026-10-10T07:32:57.440981Z"}, …]
    },
    "marketing_messages": [{"campaign": "spring", "status": "QUEUED", "created_at": "…Z", "processed_at": null}],
    "analytics_events": [{"event_name": "page_view", "occurred_at": "…Z"}],
    "omissions": [
        {"category": "credentials", "reason": "Password hash and tokens are security data, not personal data of the subject."},
        {"category": "telemetry", "reason": "Vehicle telemetry describes vehicles and is not linked to a subject."},
        {"category": "audit_events", "reason": "Audit trail holds only ids and results, kept for accountability."}
    ]
}
```

### 3.3 Демо (крок 2) — команди

```bash
B=http://localhost:8000
# токени: POST /auth/login (form: username=<email>, password=<пароль>) -> access_token
curl -s $B/api/users/1/personal-data -H "Authorization: Bearer $TOKEN_ALICE" | python -m json.tool   # власні дані: 200

curl -i $B/api/users/1/personal-data -H "Authorization: Bearer $TOKEN_BOB"     # чужий профіль
curl -i $B/api/users/9999/personal-data -H "Authorization: Bearer $TOKEN_BOB"  # неіснуючий
curl -i $B/api/users/1/personal-data                                            # без токена
```

Реальні відповіді:

```text
чужий (bob -> alice):   HTTP/1.1 404 Not Found   x-correlation-id: 6d1b862e…   {"detail":"User not found"}
неіснуючий id:          HTTP/1.1 404 Not Found   {"detail":"User not found"}
без токена:             HTTP/1.1 401 Unauthorized {"detail":"Not authenticated"}
```

### 3.4 Тести (`tests/integration/test_privacy_export.py`, 10 тестів)

| Перевірка | Тест |
|---|---|
| повнота: контрольні записи з **кожного** джерела | `test_owner_export_contains_every_source` |
| мінімізація: жодного ключа `password/token/secret/jwt`, немає хешу з БД, `$argon2`, пароля, токена, даних Bob | `test_export_never_contains_forbidden_or_foreign_data` |
| стабільна схема для користувача без даних | `test_export_has_stable_schema_for_user_without_data` |
| чужий id → 404 без даних у body | `test_stranger_gets_404_without_data` |
| неіснуючий id ≡ чужий id (однакова відповідь) | `test_nonexistent_subject_is_indistinguishable_from_foreign_one` |
| без токена / невалідний токен → 401 | `test_unauthenticated_is_401` |
| admin дозволений | `test_admin_may_export_any_subject` |
| audit без PII, результат `ok` / `denied` | `test_audit_events_record_ids_and_results_only` |
| **логи**: ні сирий, ні санітизований потік не містить PII, повного JSON, `schema_version` | `test_export_does_not_leak_pii_or_payload_into_logs` |
| correlation id у відповіді та в audit | `test_correlation_id_is_echoed_and_stored` |

---

## 4. Erasure / Anonymization (Завдання 3)

Обрано **незворотну анонімізацію** (а не фізичне видалення рядка `users`), бо оренди — бізнес/фінансові записи,
які за змодельованим retention-правилом мають зберегтися, а FK не можна ламати.

### 4.1 Політика по сутностях

| Сутність | Дія | Обґрунтування |
|---|---|---|
| `users` | **ANONYMIZE** | `email → anon-<uuid4>@anon.invalid` (унікальний), `full_name → "Anonymized User"`, `phone → NULL`, пароль → хеш випадкового, відразу відкинутого секрету, `is_active=false`, `anonymized_at` |
| `renters` | **ANONYMIZE** | `full_name`, `license_number → anon-<uuid4>` (унікальний); рядок лишається, щоб `rentals.renter_id` не став «сиротою» |
| `rentals` | **RETAIN** | змодельоване retention-правило (облік/фінанси); власних PII-колонок немає — лише id, час, статус; вказує на анонімізованого орендаря |
| `telemetry_readings` | **RETAIN** | описує авто, не суб'єкта; PII немає |
| `user_activity` | **DELETE** | суто PII/технічні ідентифікатори (IP, user-agent), підстави зберігати немає |
| `marketing_messages`, `analytics_events` | **DELETE** | поведінкові дані, ґрунтувалися на згоді |
| `user_consents` | **ANONYMIZE** | усі активні згоди відкликаються (`source=erasure`); рядки не містять PII |
| `consent_history` | **RETAIN** | доказ змін згод (accountability); лише id, purpose, версія, джерело, час — PII немає |
| `audit_events` | **APPEND** | додається одна подія без PII; старі події PII не містять (лише id) |
| Заміна значень | — | значення **випадкові й не виведені з оригіналів**: хеш email був би *псевдонімізацією* (хто знає email — перерахує й повторно ідентифікує) |

Операція — один виклик `erasure_service.anonymize_user` в **одній транзакції** (`commit` лише в кінці, `rollback` при будь-якому винятку),
рядок користувача блокується `SELECT … FOR UPDATE`. Повтор — безпечний no-op (`already_anonymized`, ідентифікатори не перегенеровуються,
нових профілів/рядків немає, додається лише audit-подія). Доступ: сам суб'єкт або admin; чужий → `404`; без токена → `401`; `GET` → `405`.

### 4.2 Демо (крок 3) — стан БД до і після

Команда (admin/суб'єкт):

```bash
curl -s -X POST $B/api/users/1/anonymize -H "Authorization: Bearer $TOKEN_ALICE" | python -m json.tool
```

**ДО** (реальний вивід `psql`):

```text
 id |            email            |    full_name    |     phone     | is_active | anonymized
----+-----------------------------+-----------------+---------------+-----------+------------
  1 | alice.synthetic@example.com | Alice Synthetic | +380000000012 | t         | f

 renters:  id=1 | full_name=Alice Synthetic | license_number=SYN-LIC-ALICE-0001 | user_id=1
 rentals:  id=1 | renter_id=1 | vehicle_id=1 | status=ACTIVE
 user_activity:      (user_id=1, login, 127.0.0.1) and (user_id=2, login, 127.0.0.1)
 user_consents:      MARKETING_EMAIL GRANTED 2026-01 web  |  OPTIONAL_ANALYTICS GRANTED 2026-01 web
 consent_history:    GRANT web, GRANT web
 marketing_messages: (user_id=1, spring, QUEUED)
 analytics_events:   (user_id=1, page_view)
 audit_events[user_anonymize]: 0 rows
```

Відповідь операції:

```json
{"subject_id": 1, "status": "anonymized", "anonymized_at": "2026-10-10T07:33:13.665934Z",
 "actions": {"renters_anonymized": 1, "activity_deleted": 1, "marketing_messages_deleted": 1,
             "analytics_events_deleted": 1, "consents_withdrawn": 2}}
```

**ПІСЛЯ** (реальний вивід `psql`):

```text
 id |                       email                        |    full_name    | phone | is_active | anonymized
----+----------------------------------------------------+-----------------+-------+-----------+------------
  1 | anon-f622ccf0a6064700bfd0ab49b7d0b02a@anon.invalid | Anonymized User |       | f         | t

 renters:  id |    full_name    |            license_number             | user_id
            1 | Anonymized User | anon-65df2bbe19b74b23b1ca7fa7e19bdd10 |       1
 rentals:   1 | renter_id=1 | vehicle_id=1 | ACTIVE                       <- збережено, FK цілі
 user_activity (user 1): 0 rows (рядок користувача 2 лишився)           marketing_messages: 0 rows    analytics_events: 0 rows

 user_consents: MARKETING_EMAIL   WITHDRAWN 2026-01 erasure   |  OPTIONAL_ANALYTICS WITHDRAWN 2026-01 erasure
 consent_history: GRANT web, GRANT web, REVOKE erasure, REVOKE erasure           (RETAIN, без PII)
 audit_events: user_anonymize | actor 1 | subject 1 | anonymized                (без PII)
```

Повтор і чужий актор (реально): токен Alice після анонімізації недійсний → `401 {"detail":"Not authenticated"}`;
Bob → `POST /api/users/1/anonymize` → `404 {"detail":"User not found"}`, дані не змінено.

### 4.3 Тести (`tests/integration/test_privacy_erasure.py`, 9 тестів)

| Властивість | Тест |
|---|---|
| оригінальних PII (email, ім'я, телефон, ліцензія) **немає в жодній текстовій колонці жодної таблиці** (перед операцією — є) | `test_anonymize_removes_pii_from_every_source` |
| оренди, FK, звітний запит `/rentals/summary` цілі; 0 «сиріт»; `consent_history` збережена | `test_business_records_survive_with_intact_references` |
| інші користувачі не зачеплені | `test_other_users_are_untouched` |
| ідемпотентність: кількості рядків незмінні (крім +1 audit), ідентифікатори ті самі | `test_second_run_is_idempotent` |
| чужий актор → 404, жодних змін | `test_stranger_is_denied_and_nothing_changes` |
| без токена → 401, `GET` → 405 | `test_unauthenticated_and_get_are_rejected` |
| логін / старий JWT анонімізованого → 401 | `test_anonymized_account_cannot_log_in_or_reuse_token` |
| **атомарність**: збій посеред workflow (monkeypatch) → повний rollback, PII на місці | `test_failure_midway_rolls_everything_back` |
| audit без PII | `test_audit_event_has_no_pii` |

---

## 5. Consent Management Engine (Завдання 4)

### 5.1 Модель

* `user_consents` — **поточний стан**, один рядок на `(user_id, purpose)` (`UNIQUE`): `purpose`, `status` (`GRANTED`/`WITHDRAWN`),
  `policy_version`, `granted_at`, `withdrawn_at`, `updated_at`, `source`.
* `consent_history` — **append-only доказ**: `purpose`, `action` (`GRANT`/`REVOKE`), `policy_version`, `source`, `occurred_at`.
  Звідси видно, яку політику прийняв користувач, коли, через який канал і коли відкликав.
* Purposes (окремі, не поширюються одне на одне): `MARKETING_EMAIL`, `OPTIONAL_ANALYTICS`, `PERSONALIZATION`. Поточна версія політики — `2026-01`.

### 5.2 API

| Метод | Шлях | Поведінка |
|---|---|---|
| `POST` | `/api/users/{id}/consents/{purpose}/grant` | body `{policy_version, source}`; ідемпотентно (та сама версія → `changed:false`, без нового рядка історії) |
| `POST` | `/api/users/{id}/consents/{purpose}/revoke` | ідемпотентно: повторний/без попереднього grant → `changed:false`, нічого не пишеться |
| `GET` | `/api/users/{id}/consents` | поточний стан + історія |
| `POST` | `/api/users/{id}/marketing-email` | **gated** `MARKETING_EMAIL` → `202` + рядок у `marketing_messages`, або `403 DENY` |
| `POST` | `/api/users/{id}/analytics-events` | **gated** `OPTIONAL_ANALYTICS` → `201` + `analytics_events`, або `403 DENY` |
| `POST` | `/api/marketing/dispatch` | (admin) фонове завдання: **перевіряє згоду перед кожним листом** — відкликані → `SKIPPED` |

Невалідний purpose → `422`; чужий id → `404`; без токена → `401`. Усі команди працюють лише для суб'єкта/admin.

### 5.3 Policy Gate

`ConsentPolicyGate.check(db, user_id, purpose, required_version)` (`services/consent_service.py`) читає рядок згоди **з БД
під час кожного виклику** (без кешу, `populate_existing`) → `ALLOW` / `DENY` з причиною: `no_consent_on_record`,
`consent_withdrawn`, `policy_version_mismatch`. При `DENY` бізнес-операція **не виконується** (немає побічного ефекту), пишеться лише audit-подія
`DENY:<причина>`. Договірні/системні функції (оренда авто) шлюз **не викликають** — тест
`test_contract_functions_are_not_blocked_by_missing_consent` доводить, що оренда працює без жодної згоди.
Для фонової черги згода перевіряється заново безпосередньо перед «відправленням» (`dispatch_pending_marketing`).

### 5.4 Демо (крок 4): GRANT → ALLOW → REVOKE → DENY (реальний вивід)

```text
1) DENY (немає згоди)   {"decision":"DENY","purpose":"MARKETING_EMAIL","reason":"no_consent_on_record"} [HTTP 403]
2) GRANT                {"purpose":"MARKETING_EMAIL","status":"GRANTED","policy_version":"2026-01","granted_at":"2026-10-10T07:33:22.152601Z","withdrawn_at":null,"source":"web","changed":true}
3) ALLOW                {"decision":"ALLOW","message_id":2,"status":"QUEUED"} [HTTP 202]
4) REVOKE               {"purpose":"MARKETING_EMAIL","status":"WITHDRAWN",…,"withdrawn_at":"2026-10-10T07:33:22.710812Z","source":"api","changed":true}
5) DENY після відкликання {"decision":"DENY","purpose":"MARKETING_EMAIL","reason":"consent_withdrawn"} [HTTP 403]
```

Відсутність побічного ефекту після REVOKE (`psql`): у `marketing_messages` для користувача 2 — **один** рядок (з кроку 3), крок 5 нового не створив;
`consent_history`: `GRANT | 2026-01 | web | 07:33:22.152601+00` → `REVOKE | 2026-01 | api | 07:33:22.710812+00`.

Завершити демо запуском інтеграційного тесту:

```powershell
pytest tests/integration/test_privacy_consent.py::test_grant_allow_revoke_deny_scenario -v
pytest tests/integration/test_privacy_consent.py -v
```

### 5.5 Тести (`tests/integration/test_privacy_consent.py`, 12 тестів)

`test_grant_allow_revoke_deny_scenario` (DENY → GRANT → ALLOW + side effect → REVOKE → DENY без нового side effect),
`test_consent_for_one_purpose_does_not_allow_another` (ізоляція purposes), `test_stale_policy_version_is_denied`,
`test_grant_and_revoke_are_idempotent`, `test_state_and_history_keep_evidence` (version/timestamps/source/історія),
`test_invalid_purpose_is_rejected`, `test_stranger_cannot_manage_foreign_consent`,
`test_background_job_rechecks_consent_before_sending` (відкликано після постановки в чергу → `SKIPPED`),
`test_background_job_sends_while_consent_holds`, `test_gate_reads_fresh_state_each_call`,
`test_admin_dispatch_endpoint_requires_admin`, `test_contract_functions_are_not_blocked_by_missing_consent`.

---

## 6. Маскування, псевдонімізація, анонімізація, видалення

| Техніка | Що робить | Оборотність | Де в роботі |
|---|---|---|---|
| **Маскування** | приховує частину значення для читача (`a***@example.com`) | оригінал існує деінде | логи |
| **Псевдонімізація** | замінює ідентифікатор іншим, який можна зв'язати з оригіналом окремим ключем/таблицею/хешем | **оборотна** (за наявності ключа) → усе ще ПД за GDPR | свідомо **не** використана для erasure: хеш email — це псевдонімізація |
| **Анонімізація** | незворотно прибирає зв'язок з особою; значення випадкові, не виведені з оригіналу | **необоротна** | `users`, `renters` при erasure |
| **Видалення** | фізично прибирає запис | — | `user_activity`, `marketing_messages`, `analytics_events` |

Обрані механізми відповідають меті: для логів потрібна діагностика без розкриття (маскування), для оренд — зберегти бізнес-запис без
можливості повторної ідентифікації (анонімізація), для суто поведінкових/технічних даних підстав зберігати немає (видалення).

---

## 7. Підсумковий технічний висновок

| Механізм | Усуває ризик | Чим доведено |
|---|---|---|
| Централізований sanitizer + body-free access log | витік PII/секретів у журнали (будь-який шар, будь-який формат, винятки) | 13 unit-тестів, негативний контроль, перевірка логу живого сервера |
| Personal Data Export (subject/admin, 404, explicit-схема) | IDOR, надлишкова відповідь, витік хешу/токенів, перебір id | 10 інтеграційних тестів (повнота, мінімізація, 401/404, логи) |
| Anonymization workflow (транзакція, ідемпотентність, random-значення) | збереження PII у пов'язаних сутностях, оборотність, часткове виконання | 9 інтеграційних тестів (скан усіх текстових колонок, rollback, FK) |
| Consent engine + Policy Gate | «формальна» згода без впливу на поведінку | 12 інтеграційних тестів (GRANT→ALLOW→REVOKE→DENY, ізоляція, фонове завдання) |

**Результати перевірок:** `pytest tests` — **1315 passed**; `ruff check .` / `ruff format --check .` — чисто; `xenon --max-absolute B src`
і `complexipy --max-complexity-allowed 15` — у нормі; `alembic upgrade head` на порожній БД і `downgrade -1`/`upgrade head` — успішно,
`alembic check` — «No new upgrade operations detected»; `gitleaks dir` — «no leaks found».

**Поза межами програмної реалізації (потребує організаційних/юридичних рішень):** законна підстава обробки для кожної мети (Art. 6) та
чи є згода правильною підставою; строки зберігання (retention) оренд, audit і `consent_history` (у лабораторній — змодельоване правило «RETAIN»);
резервні копії та реплікація (стирання в бекапах); процес і SLA обробки запитів суб'єктів (верифікація особи, терміни 30 днів);
повідомлення про витоки (Art. 33/34), DPIA, реєстр обробки, договори з процесорами та міжнародні передачі; тексти політик і їх версіонування юридично;
мінімальний вік / згода батьків. Програмні контролі лише забезпечують виконання вже ухвалених правил.
