# Звіт: Лабораторна робота №7 — Інформаційна складність за Чепіним та Hotspots у CI/CD

**Застосунок:** Fleet Management (каршерінг): FastAPI + PostgreSQL + Redis + RabbitMQ, Python 3.13
**Гілка:** `feat/lab7-chapin-hotspots` (від `main`, без окремого worktree і без пайплайну розробки)
**Сирі виводи команд:** [`outputs/`](outputs/)

> **Стан доказів.** Усі числа нижче отримані реальними командами (файли в `outputs/`). Єдине, чого тут ще немає, — **скріншота успішного запуску у GitHub Actions**: workflow [`hotspots.yml`](../../.github/workflows/hotspots.yml) закомічено, але гілку ще не запушено, тому в хмарі він не виконувався. Після `git push` у вкладці Actions з'явиться job `Hotspots` з артефактом `hotspots-report` — саме його скріншот треба додати у розділ 3.1. Локально той самий сценарій відпрацьовано (розділ 3.2–3.3).

---

## Завдання 1. Семантичний аудит за Чепіним

### 1.1 Декларація об'єкта аналізу

| Поле | Значення |
|---|---|
| Метод | `dispatch_pending_marketing(db)` — `src/fleet_management/services/marketing_service.py` |
| Архітектурна роль | Інтеграційний контур: фонова розсилка маркетингових листів. Для кожного повідомлення з черги заново питає Consent Policy Gate (GDPR-згода) і переводить рядок БД у `SENT`/`SKIPPED`. Помилка тут = лист клієнту без згоди або «фантомне» відправлення. |
| Цикломатична складність (Мак-Кейб) | **CC = 4** (клас A) — [`outputs/01-baseline-radon-cc.txt`](outputs/01-baseline-radon-cc.txt). Критерій відбору CC ≤ 5 виконано: код лінійний (один цикл, два тернарні вирази), але інтенсивно працює зі станом. |
| Код «до» | [`outputs/00-before-dispatch_pending_marketing.py.txt`](outputs/00-before-dispatch_pending_marketing.py.txt) |

```python
async def dispatch_pending_marketing(db: AsyncSession) -> dict[str, int]:
    queued = (...await db.execute(select(MarketingMessage).where(status == QUEUED))...).scalars().all()
    counts = {"sent": 0, "skipped": 0}
    for message in queued:
        decision = await ConsentPolicyGate.check(db, message.user_id, ConsentPurpose.MARKETING_EMAIL)
        message.status = MarketingStatus.SENT if decision.allowed else MarketingStatus.SKIPPED
        message.processed_at = datetime.now(UTC)
        counts["sent" if decision.allowed else "skipped"] += 1
    await db.commit()
    return counts
```

### 1.2 Правила класифікації (застосовано однаково до «до» і «після»)

* Змінна = параметр або ім'я, що зв'язується в тілі (включно зі змінною циклу). Імена класів, функцій, enum-констант (`MarketingStatus`, `select`) змінними не вважаються.
* Ієрархія: **C → M → P → T** (найвища вага перемагає).
* **C** — бере участь в умові (`if`/тернарний вираз/цикл-умова). **M** — сама змінна перез'єднується або її стан змінюється (присвоєння атрибута, `+=`). **P** — лише читається. **T** — лише передається далі без читання вмісту.

### 1.3 Семантична матриця Чепіна (стан ДО)

| Змінна | Тип | Клас | Обґрунтування | Вага |
|---|---|---|---|---:|
| `db` | `AsyncSession` | **T** | Приймається ззовні й лише прокидається в `db.execute`, `ConsentPolicyGate.check`, `db.commit`; в умовах не бере участі | 0.5 |
| `queued` | `Sequence[MarketingMessage]` | **P** | Присвоюється один раз, потім лише читається в `for` | 1 |
| `counts` | `dict[str, int]` | **M** | Лічильник змінюється `+= 1` у циклі, ключ обирається умовою | 2 |
| `message` | `MarketingMessage` (ORM) | **M** | Змінна циклу; у тілі перезаписуються `message.status` і `message.processed_at` (також читається `user_id`) — M вища за P | 2 |
| `decision` | `GateDecision` | **C** | `decision.allowed` керує двома тернарними виразами — це і є бізнес-рішення | 3 |

Кількість: **P = 1, M = 2, C = 1, T = 1**.

### 1.4 Розрахунок

```
C_ch = 1·P + 2·M + 3·C + 0.5·T
     = 1·1 + 2·2 + 3·1 + 0.5·1
     = 1 + 4 + 3 + 0.5
     = 8.5
```

**Висновок про ризик.** 8.5 не перевищує enterprise-межу 10 («архітектурний хаос»), тож це не катастрофа, але метод перевищує еталон чистої функції (≤ 6). Головний внесок — **два M-класи (4 з 8.5)**: рядки БД і лічильник міняються *під час* ухвалення рішень. Це дає два реальних дефекти мутації, які й відтворено в Завданні 2: (1) збій посеред циклу залишає частину рядків уже в стані `SENT`; (2) `processed_at` береться заново для кожного рядка, тож один прогін має «розповзлі» мітки часу. Топологічна метрика цього не бачить: CC = 4.

> Чесне застереження щодо вибірки: у методі 5 змінних — це не «1–2», але й не десятки. Щоб це не було самоціллю, правила класифікації зафіксовано вище й застосовано без підгонки до результату.

---

## Завдання 2. Імутабельність та Value Objects

### 2.1 Симуляція збою (FAIL) — коміт `f6e21cb`

Файл: [`tests/unit/test_marketing_dispatch_mutation.py`](../../tests/unit/test_marketing_dispatch_mutation.py). Два краш-тести проти мутабельної реалізації:

1. **`test_gate_failure_midway_must_not_leave_phantom_sent_messages`** — gate відповідає ALLOW для повідомлення 1 і падає на повідомленні 2. Нічого не закомічено, тому повідомлення 1 мусить лишитись `QUEUED`. Мутабельний цикл уже записав йому `SENT`.
2. **`test_one_batch_shares_one_immutable_processed_at`** — один прогін має мати один момент обробки; мутабельний цикл знову читає годинник на кожному рядку.

Результат на мутабельному коді ([`outputs/02-fail-pytest-mutation.txt`](outputs/02-fail-pytest-mutation.txt)):

```
E  assert <MarketingStatus.SENT: 'SENT'> == <MarketingStatus.QUEUED: 'QUEUED'>
E  AssertionError: processed_at drifted inside one batch
E  assert 3 == 1
FAILED ...::test_gate_failure_midway_must_not_leave_phantom_sent_messages
FAILED ...::test_one_batch_shares_one_immutable_processed_at
2 failed
```

Коміт: `feat(audit): simulate data mutation issue, FAIL`.

### 2.2 Архітектурний рефакторинг — коміт `33a71b7`

**Імутабельність.** Рішення ухвалюються *першими* і лише створюють значення; рядки БД змінюються в єдиному місці (`DispatchOutcome.apply`) *після* того, як усі вердикти вже існують. Акумулятор `counts` зник: підсумок обчислюється з кортежу вердиктів. Колекція вердиктів — `tuple`, а не `list`.

**Value Object.** Розрізнені `message` / `decision.allowed` / момент обробки згруповано в `@dataclass(frozen=True) DispatchOutcome`. Логіку вибору статусу (`SENT`/`SKIPPED`) перенесено всередину VO — властивість `status`; тернарний вираз більше не живе в методі. Єдиний момент часу створюється один раз і розділяється всіма вердиктами.

**Порівняння «до / після»:**

| ДО (мутабельний цикл) | ПІСЛЯ (імутабельні вердикти) |
|---|---|
| ```python
counts = {"sent": 0, "skipped": 0}
for message in queued:
    decision = await ConsentPolicyGate.check(
        db, message.user_id, MARKETING_EMAIL)
    message.status = SENT if decision.allowed else SKIPPED
    message.processed_at = datetime.now(UTC)
    counts["sent" if decision.allowed else "skipped"] += 1
await db.commit()
return counts
``` | ```python
outcomes = await _decide_queue(db, datetime.now(UTC))
for outcome in outcomes:
    outcome.apply()
await db.commit()
return _summary(outcomes)
``` |

Повний новий код — [`marketing_service.py`](../../src/fleet_management/services/marketing_service.py); diff — [`outputs/05-diff-fail-to-pass.diff`](outputs/05-diff-fail-to-pass.diff).

### 2.3 Повторна верифікація за Чепіним (стан ПІСЛЯ)

Метод `dispatch_pending_marketing`:

| Змінна | Клас | Обґрунтування | Вага |
|---|---|---|---:|
| `db` | **T** | Лише прокидається в `_decide_queue` і `commit` | 0.5 |
| `outcomes` | **P** | Незмінний кортеж: читається в циклі й передається в `_summary` | 1 |
| `outcome` | **P** | Змінна циклу, лише читається (`apply()` не перез'єднує змінну) | 1 |

```
C_ch = 1·2 + 2·0 + 3·0 + 0.5·1 = 2 + 0.5 = 2.5
```

**8.5 → 2.5: падіння у 3.4 раза** (вимога ≥ 2× і ≤ 6 виконана). `M = 0`, `C = 0` у самому методі.

Нові одиниці, які з'явилися (той самий метод класифікації):

| Одиниця | P | M | C | T | C_ch |
|---|---:|---:|---:|---:|---:|
| `_decide_queue` (`queued`; `db`,`processed_at`,`message` — T) | 1 | 0 | 0 | 3 | 2.5 |
| `_verdict` (`message`,`decision` — P; `db`,`processed_at` — T) | 2 | 0 | 0 | 2 | 3.0 |
| `_summary` (`outcomes`,`outcome`,`tally` — P) | 3 | 0 | 0 | 0 | 3.0 |
| `DispatchOutcome.status` / `.apply` (`self` — P) | 1 | 0 | 0 | 0 | 1.0 / 1.0 |

Жодна одиниця не перевищує 3.0 (≤ 6).

**Чесне застереження.** Сума по всіх одиницях (2.5+2.5+3+3+1+1 = 13) *більша* за 8.5 вихідного методу: логіка розподілена на малі функції. Метрика Чепіна в лабі — на рівні методу, і тут вона впала втричі, а найгірша окрема одиниця — 3.0 проти 8.5. Але це не «безкоштовне» зменшення: загальна кількість змінних на модуль зросла, і виграш тримається саме на тому, що **M зникли**, а не на самому розбитті (Extract Method без імутабельності дав би ті самі M). Запис у ORM (`message.status = ...`) нікуди не зник — його локалізовано в `apply()` і відкладено до моменту, коли всі рішення вже ухвалені; повністю прибрати його без відмови від ORM-сутностей неможливо.

### 2.4 PASS

Коміт `33a71b7`: `refactor(audit): reduce Chapin complexity using immutable Value Objects, PASS`.

* Краш-тести тепер проходять; додано тест, що VO справді імутабельний (`FrozenInstanceError`) і що `status` не торкається рядка до `apply()` — [`outputs/03-pass-pytest-mutation.txt`](outputs/03-pass-pytest-mutation.txt): `4 passed`.
* Увесь юніт-набір: `1306 passed` на момент коміту. Інтеграційні тести (`test_privacy_consent.py`, `test_api.py`) перевірено проти тимчасових Postgres 16 і Redis 7 у Docker: `23 passed`, включно з реальним `dispatch`.
* CC після: `dispatch_pending_marketing` = 2 (було 4) — [`outputs/04-pass-radon-cc.txt`](outputs/04-pass-radon-cc.txt); `xenon --max-absolute B src` і `complexipy` (≤ 15) проходять.

### 2.5 Git History

```
* 06d90c6 feat(infra): add hotspots workflow (radon JSON x git churn matrix)
* 33a71b7 refactor(audit): reduce Chapin complexity using immutable Value Objects, PASS
* f6e21cb feat(audit): simulate data mutation issue, FAIL
*   abba681 (main) Merge pull request #30 from YakymivDanylo/demo/reset
```

Дерево: [`outputs/09-git-graph.txt`](outputs/09-git-graph.txt). Скріншот для захисту — `git log --graph --oneline`.

---

## Завдання 3. Хмарний моніторинг та матриця Hotspots

### 3.1 Код автоматизації CI/CD

Файл [`.github/workflows/hotspots.yml`](../../.github/workflows/hotspots.yml) (повний лістинг):

```yaml
name: Hotspots

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  hotspots:
    name: Complexity x Churn matrix
    runs-on: ubuntu-latest
    container:
      image: python:3.13          # скан у Docker-контейнері; в образі є git
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # повна історія — потрібна для churn
      - run: git config --global --add safe.directory "$GITHUB_WORKSPACE"
      - run: pip install radon==6.0.1
      - name: Complexity scan of the whole repository (JSON)
        run: |
          mkdir -p hotspots-report
          radon cc  . -j --exclude ".venv/*,node_modules/*,alembic/*" > hotspots-report/complexity.json
          radon hal . -j --exclude ".venv/*,node_modules/*,alembic/*" > hotspots-report/halstead.json
      - name: Churn rate, last 90 days (git log)
        run: |
          git log --since="90 days ago" --format=format: --name-only \
            | grep -Ev '^$' | sort | uniq -c | sort -nr | tee hotspots-report/churn-90d.txt
      - run: python scripts/hotspots.py --radon-json hotspots-report/complexity.json --out-dir hotspots-report | tee -a "$GITHUB_STEP_SUMMARY"
      - uses: actions/upload-artifact@v4
        with:
          name: hotspots-report
          path: hotspots-report/
          if-no-files-found: error
```

(У файлі в репозиторії додатково є `concurrency`, `permissions: contents: read` та коментарі.) Вимоги лаби: встановлення сканера на кожен push/PR ✔, скан усього репозиторію в JSON ✔, збереження як Build Artifact ✔, виконання в Docker-контейнері ✔. Логіку матриці винесено в [`scripts/hotspots.py`](../../scripts/hotspots.py) (стандартна бібліотека, 4 юніт-тести в `tests/unit/test_hotspots.py`). Синтаксис YAML перевірено парсером; **у хмарі ще не запускалось** (див. примітку нагорі).

### 3.2 Лог метрик процесу (Churn Rate, 90 днів)

Команда (вимога лаби + вікно 90 днів):

```bash
git log --since="90 days ago" --format=format: --name-only | grep -Ev '^$' | sort | uniq -c | sort -nr
```

Історія в межах вікна: 2026-09-04 … 2026-10-29. Верх виводу (повний — [`outputs/07-churn-90d.txt`](outputs/07-churn-90d.txt), 394 рядки):

```
     15 .github/workflows/ci.yml
     14 README.md
     12 src/fleet_management/main.py
     12 pyproject.toml
     11 src/fleet_management/config.py
      8 src/fleet_management/services/rental_service.py
      8 requirements-dev.txt
      8 docker-compose.yml
      7 .env.example
      6 src/fleet_management/schemas.py
      6 scripts/seed_loadtest.py
      6 Dockerfile
      5 src/fleet_management/api/rentals.py
```

Це **ретроспективний аудит (Варіант 1)** — використано реальну історію власного репозиторію (160 комітів), штучне наповнення не потрібне. Примітка: лічильники включають три коміти цієї лаби.

### 3.3 Синергетична матриця Hotspots

Метрика складності — **сума CC усіх блоків файлу** (radon JSON, [`outputs/06-complexity.json`](outputs/06-complexity.json)), у дужках — максимум по блоках. Повна матриця (усі `.py`-файли) — [`outputs/08-hotspots-matrix.md`](outputs/08-hotspots-matrix.md). Ключові файли застосунку:

| Файл | Σ CC (max блок) | Комітів (90 дн.) | Категорія |
|---|---:|---:|---|
| `services/rental_service.py` | 32 (4) | 8 | **Hotspot** (червона) |
| `config.py` | 14 (4) | 11 | **Active** (зелена) |
| `main.py` | 7 (4) | 12 | **Active** (зелена) |
| `api/rentals.py` | 15 (4) | 5 | **Active** (зелена) |
| `services/vehicle_state_service.py` | 26 (9) | 2 | **Sleeping** (жовта) |
| `services/consent_service.py` | 31 (5) | 1 | **Sleeping** (жовта) |
| `privacy/logging_setup.py` | 41 (10) | 1 | **Sleeping** (жовта) |
| `services/marketing_service.py` | 17 (3) | 2 | **Stable** (сіра) |
| `models/user.py` | 2 (1) | 3 | **Stable** (сіра) |

Пороги: Σ CC ≥ 25 — «складний», комітів ≥ 5 — «мінливий» (параметри `--cc-threshold`, `--churn-threshold`).

**Чому не «CC > 10» з методички.** У репозиторії діє воротар `xenon --max-absolute B` (CC ≤ 10 на блок), тож жоден окремий блок не може перевищити 10 — критерій «CC > 10» не розрізняв би жодного файлу. Тому за міру взято суму CC файлу (метрика лаби дозволяє «CC або Effort»). Пороги 25 і 5 — моє рішення, а не стандарт: їх обрано так, щоб відокремити верхню частину розподілу, і вони змінюють склад категорій; це чесно слід озвучити на захисті.

### 3.4 Аналіз і пріоритети на наступний спринт

1. **`rental_service.py` — єдиний Hotspot у застосунку.** 8 змін за квартал і Σ CC = 32. Усередині одного модуля живуть життєвий цикл оренди, політика знижок (таблиці з ЛР6), перевірка допуску та ще 17 блоків. Кожен блок простий (max CC = 4), тож це «god module» за **обсягом відповідальностей**, а не за топологією. *Рекомендація:* розділити на `rental_lifecycle.py`, `discount_policy.py`, `eligibility.py`; це знижує конфлікти при паралельній роботі, а регресійний ризик закритий golden-master тестом `test_discount_equivalence.py`. Пріоритет №1.
2. **`config.py`, `main.py`, `api/rentals.py` — Active (ідеальний стан).** Багато правок при низькій складності: конфігурація і композиція росте, але лишається лінійною. Рефакторинг не потрібен; лише слідкувати, щоб `config.py` (11 комітів) не накопичив логіки.
3. **`logging_setup.py` (41, max 10), `vehicle_state_service.py` (max 9), `consent_service.py` — Sleeping.** Складні, але їх майже не міняють. Блоки `logging_setup.py` і `vehicle_state_service.py` впритул до воротаря CC ≤ 10. *Рекомендація:* не чіпати зараз; рефакторити лише при наступному Change Request у цих областях.
4. **`marketing_service.py` — Stable.** Після ЛР7 Σ CC = 17, 2 коміти (обидва — з цієї лаби). Мета «опинитися в сірій зоні» досягнута.

Окремо: `scripts/seed_loadtest.py` теж потрапив у Hotspot (32 / 6), але це допоміжний скрипт для навантажувального тесту, не продакшн-код — пріоритет низький.

---

## Відтворення

```bash
git checkout f6e21cb && pytest tests/unit/test_marketing_dispatch_mutation.py   # FAIL
git checkout 33a71b7 && pytest tests/unit/test_marketing_dispatch_mutation.py   # PASS
radon cc . -j --exclude ".venv/*" > complexity.json
python scripts/hotspots.py --radon-json complexity.json --out-dir hotspots-report
git log --since="90 days ago" --format=format: --name-only | grep -Ev '^$' | sort | uniq -c | sort -nr
```
