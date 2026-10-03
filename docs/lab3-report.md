# Лабораторна робота №3 — Maintainability Refactoring та Software Supply Chain Security

Гайд «як показати на захисті» — у [`lab3-demo.md`](lab3-demo.md). Сирі звіти аналізаторів — у [`lab3/reports/`](lab3/reports/).

## 1. Характеристика проєкту та інструментів

**Проєкт:** Fleet Management — station-based carsharing з IoT-телеметрією. FastAPI (REST API) + PostgreSQL (SQLAlchemy async, Alembic) + RabbitMQ (потік телеметрії, `telemetry-worker`) + Redis (кеш стану авто), JWT-автентифікація.

| Що | Де |
|---|---|
| Runtime-залежності (потрапляють у Docker-образ) | `requirements.txt` (pinned) |
| Dev/CI-залежності | `requirements-dev.txt` (`-r requirements.txt` + інструменти) |
| Метадані пакета | `pyproject.toml` |
| Тести | `pytest` — `tests/unit` (без зовнішніх сервісів), `tests/integration` (Postgres + Redis) |

| Призначення | Інструмент | Версія | Команда |
|---|---|---|---|
| Cyclomatic Complexity | radon | 6.0.1 | `radon cc <path> -s` |
| Gate для Cyclomatic (≤ 10, rank B) | xenon | 0.9.3 | `xenon --max-absolute B src` |
| Cognitive Complexity (специфікація SonarSource) | complexipy | 8.0.1 | `complexipy <path>` / `complexipy src --max-complexity-allowed 15` |
| SCA | pip-audit (база PyPI Advisory / OSV) | 2.10.1 | `pip-audit -r requirements-dev.txt`, `pip-audit -l` |
| Secret scanner | gitleaks (через pre-commit hook) | 8.30.1 | `pre-commit run gitleaks`, автоматично на `git commit` |
| Hook-фреймворк | pre-commit | 4.6.2 | `pre-commit install` |

Усі інструменти зафіксовані в `requirements-dev.txt` / `.pre-commit-config.yaml` і запускаються в CI (`.github/workflows/ci.yml`, jobs `complexity`, `sca`, `secrets`).

## 2. Вимірюваний рефакторинг

### 2.1 Вибір ділянки та baseline

Скан усього `src/` (`radon cc src -s -n B`, `complexipy src -s desc`) показав, що єдиний блок, який перевищує поріг, — `validate_rental_eligibility` у `src/fleet_management/services/rental_service.py`:

| Функція | Cyclomatic (radon) | Cognitive (complexipy) |
|---|---|---|
| **`validate_rental_eligibility`** | **11 (rank C) — > 10** | **11** |
| `vehicle_state_service.get_vehicle_state` | 6 | 9 |
| `resilience.call_with_retry` | 4 | 6 |

Cognitive Complexity 11 не перевищує 15, але **Cyclomatic 11 > 10** — умова завдання виконана. Причина складності: 9 вхідних прапорців, вкладений `if has_unpaid_fees:` з двома гілками всередині, складений булевий вираз `deposit_missing` (`and ... and not ...`) та 8 послідовних `return`, порядок яких неявно задає пріоритет правил.

Baseline повністю — [`lab3/reports/complexity-before.txt`](lab3/reports/complexity-before.txt) (модуль: MI = 36.96, SLOC = 110). Код «до»:

```python
def validate_rental_eligibility(renter_is_blacklisted, license_expired, has_unpaid_fees,
        active_rental_count, vehicle_status, station_is_open, is_weekend,
        weekend_requires_deposit, has_deposit_on_file) -> tuple[bool, str]:
    if renter_is_blacklisted:
        return False, "Renter is blacklisted"
    if license_expired:
        return False, "License expired"

    deposit_missing = is_weekend and weekend_requires_deposit and not has_deposit_on_file

    if has_unpaid_fees:
        if active_rental_count > 0:
            return False, "Unpaid fees with an active rental"
        if deposit_missing:
            return False, "Deposit required for unpaid fees on weekend"

    if vehicle_status != VehicleStatus.AVAILABLE:
        return False, "Vehicle not available"
    if not station_is_open:
        return False, "Station is closed"
    if deposit_missing:
        return False, "Deposit required on weekend"

    return True, "OK"
```

### 2.2 Захисні тести (до рефакторингу)

1. **Golden master** — `tests/unit/test_rental_eligibility_characterization.py`: заморожена копія старої реалізації порівнюється з поточною на **всьому просторі входів** — 2⁷ булевих комбінацій × `active_rental_count ∈ {0, 1, 3}` × 3 статуси авто = **1152 кейси**. Будь-яка зміна результату або пріоритету правил ламає тест.
2. **Граничні/пріоритетні сценарії** — `test_validate_rental_eligibility_rule_priority_and_edges` у `tests/unit/test_rental_service.py` (7 нових кейсів): `active_rental_count = 0` vs `1` (межа), борг + активна оренда + вихідний без депозиту (який із двох порушень виграє), `MAINTENANCE`, недоступне авто + закрита станція, `is_weekend` без вимоги депозиту і навпаки.

На baseline-коді: `pytest tests/unit` → **1224 passed**.

### 2.3 Застосовані техніки

| Техніка | Проблема, яку вона усуває |
|---|---|
| **Introduce Parameter Object** → `RentalEligibilityContext` (frozen dataclass) | 9 позиційних прапорців без структури; правила не можна винести, бо їм треба передавати всі 9 значень |
| **Decompose Conditional / Extract Method** → `deposit_missing`, `unpaid_fees_with_active_rental()`, `unpaid_fees_without_deposit()`, `vehicle_unavailable()`, `station_closed()` | Складені булеві вирази й вкладений `if` змішували *що* перевіряємо з *як*; тепер кожна умова — іменований предикат |
| **Replace Nested Conditional with Rule Table** (table-driven rules / спрощений Chain of Responsibility) → `ELIGIBILITY_RULES` | Ланцюжок із 8 `if/return` і вкладеністю, де пріоритет правил закодовано неявно порядком гілок. Тепер пріоритет — явний порядок у кортежі, а функція — один цикл |

Код «після»:

```python
@dataclass(frozen=True)
class RentalEligibilityContext:
    ...  # 9 полів

    @property
    def deposit_missing(self) -> bool:
        return self.is_weekend and self.weekend_requires_deposit and not self.has_deposit_on_file

    def unpaid_fees_with_active_rental(self) -> bool:
        return self.has_unpaid_fees and self.active_rental_count > 0

    def unpaid_fees_without_deposit(self) -> bool:
        return self.has_unpaid_fees and self.deposit_missing
    ...

# Ordered by priority: the first violated rule determines the rejection reason.
ELIGIBILITY_RULES: tuple[EligibilityRule, ...] = (
    (attrgetter("renter_is_blacklisted"), "Renter is blacklisted"),
    (attrgetter("license_expired"), "License expired"),
    (RentalEligibilityContext.unpaid_fees_with_active_rental, "Unpaid fees with an active rental"),
    (RentalEligibilityContext.unpaid_fees_without_deposit, "Deposit required for unpaid fees on weekend"),
    (RentalEligibilityContext.vehicle_unavailable, "Vehicle not available"),
    (RentalEligibilityContext.station_closed, "Station is closed"),
    (attrgetter("deposit_missing"), "Deposit required on weekend"),
)

def validate_rental_eligibility(...same 9 params...) -> tuple[bool, str]:
    ctx = RentalEligibilityContext(...)
    for is_violated, reason in ELIGIBILITY_RULES:
        if is_violated(ctx):
            return False, reason
    return True, "OK"
```

Публічна сигнатура не змінилась — викликачі та тести не чіпались. Предикати — іменовані методи, а не лямбди: складність не «ховається» від аналізатора, вона перерозподілена на маленькі блоки, кожен з яких radon/complexipy міряє окремо.

### 2.4 Порівняння метрик (той самий інструмент, та сама конфігурація)

| Показник | До | Після |
|---|---|---|
| Cyclomatic Complexity `validate_rental_eligibility` (radon) | **11 (C)** | **3 (A)** |
| Cognitive Complexity `validate_rental_eligibility` (complexipy) | **11** | **3** |
| Макс. Cyclomatic серед нових предикатів | — | 3 (`deposit_missing`) |
| Макс. Cognitive серед нових предикатів | — | 1 |
| Max Cyclomatic у модулі | 11 | 4 |
| Maintainability Index модуля (radon mi) | 36.96 | 38.94 |
| SLOC модуля | 110 | 146 (+ dataclass і таблиця правил) |
| `xenon --max-absolute B` (CC ≤ 10) | **FAIL** (rank C) | **PASS** |
| Regression tests | 1224 passed | **1224 passed** (повний набір з integration — 1269 passed) |

Чесна ціна: SLOC зріс, бо з'явились явні імена для кожного правила. Зате функція, яку читають і змінюють, тепер має 1 рівень вкладеності, а нове правило додається одним рядком у таблицю без зміни керувального потоку.

**Cyclomatic vs Cognitive.** Cyclomatic (McCabe) = кількість лінійно незалежних шляхів: +1 за кожне розгалуження і кожен `and`/`or`; показує, *скільки тестів* потрібно для покриття гілок. Cognitive (SonarSource) — *наскільки важко прочитати*: +1 за розрив лінійного потоку, **додатковий штраф за вкладеність**, а послідовність однакових булевих операторів рахується один раз. Тому вкладений `if has_unpaid_fees: if ...:` давав Cognitive штраф за вкладеність, а три `and` у `deposit_missing` — +2 до Cyclomatic. Rule table прибрав і вкладеність, і булеві оператори з тіла функції — обидві метрики впали до 3.

Звіт «після» — [`lab3/reports/complexity-after.txt`](lab3/reports/complexity-after.txt). Щоб складність не повзла назад, у CI додано job `complexity`: `xenon --max-absolute B src` і `complexipy src --max-complexity-allowed 15`.

## 3. SCA Security Audit

### 3.1 Налаштування

- Інструмент: **pip-audit 2.10.1** (PyPA), джерело — PyPI Advisory DB / OSV.
- Аналізовані файли: `requirements.txt` (runtime) і `requirements-dev.txt` (dev + CI), а також **реально встановлене середовище** `.venv` (`pip-audit -l`), де видно транзитивні версії, які `requirements*.txt` не фіксують.

### 3.2 Первинне сканування

| Скан | Компонентів | Critical | High | Medium | Low |
|---|---|---|---|---|---|
| `pip-audit -r requirements.txt` (runtime / Docker-образ) | 41 | 0 | 0 | 0 | 0 |
| `pip-audit -r requirements-dev.txt` (свіжий resolve, вихідний файл) | 60 | 0 | 0 | 0 | 0 |
| **`pip-audit -l` (встановлений `.venv`)** | **88** | **0** | **3** | **1** | **0** |

Звіти: [`sca-before.txt`](lab3/reports/sca-before.txt), [`sca-before.json`](lab3/reports/sca-before.json). Severity — з GitHub Advisory Database (`gh api advisories/<GHSA>`).

| Компонент | Installed | Fixed | Direct/transitive | Advisory / CVE | Severity | Рішення |
|---|---|---|---|---|---|---|
| virtualenv | 21.7.8 | 21.7.12 | transitive (`pre-commit 4.6.2 → virtualenv`) | GHSA-94p9-xgh2-xp45 / CVE-2026-102930 — завантажені seed-wheels не перевіряються за хешем | High | Оновлено до 21.14.5 |
| virtualenv | 21.7.8 | 21.7.12 | transitive | **GHSA-x78j-v8h9-3j2q / CVE-2026-102937** — command injection через `--prompt` в `activate.bat` | High | Оновлено до 21.14.5 |
| virtualenv | 21.7.8 | 21.7.13 | transitive | GHSA-p58f-9548-mpm2 / CVE-2026-102925 — виконання команд з шляху в `activate` (bash/fish), CVSS 7.8 | High | Оновлено до 21.14.5 |
| virtualenv | 21.7.8 | 21.7.11 | transitive | GHSA-9h9j-4vrj-gf7g / CVE-2026-102938 — інʼєкція ключів у `pyvenv.cfg` через prompt | Medium | Оновлено до 21.14.5 |

### 3.3 Детальний тріаж: GHSA-x78j-v8h9-3j2q (CVE-2026-102937, High)

- **Бібліотека / версія:** `virtualenv 21.7.8`, виправлено в `21.7.12`.
- **Шлях потрапляння:** transitive, dev-only: `requirements-dev.txt → pre-commit==4.6.2 → virtualenv` (`pip show virtualenv` → `Required-by: pre_commit`). `pre-commit` використовує virtualenv, щоб створювати ізольовані середовища для хуків (`~/.cache/pre-commit`).
- **Суть:** `BatchActivator.quote()` не екранує значення. Prompt (з `--prompt`, змінної `VIRTUALENV_PROMPT` або конфіг-файлу) записується в `activate.bat` як `@set "VAR=value"`; подвійна лапка в prompt закриває рядок, і решта виконується як команди `cmd.exe` у момент активації venv.
- **Досяжність у нашому проєкті:** проєкт розробляється на **Windows**, тобто `activate.bat` реально використовується. Prompt ми не задаємо з недовірених даних, але `VIRTUALENV_PROMPT` читається з оточення — будь-який процес/скрипт, що може виставити змінну оточення (наприклад, CI-job, що бере назву гілки), отримав би code execution на машині розробника. У **runtime Docker-образ** virtualenv не потрапляє (`Dockerfile` ставить тільки `requirements.txt`), тож продакшн-сервіс не зачеплено — ризик стосується ланцюга постачання розробки.
- **Чому проблема не видна в `requirements-dev.txt`:** транзитивна версія не була зафіксована. Свіжий `pip install` у CI бере актуальний virtualenv, а локальний `.venv`, створений раніше, лишається з вразливою версією — середовища розробника і CI розійшлися.
- **Рішення:** оновлення (а не прийняття ризику — виправлена версія існує й сумісна з `pre-commit`, якому потрібне `virtualenv>=20.10`). У `requirements-dev.txt` транзитивну залежність явно запінено з коментарем-посиланням на advisory:
  ```
  # Transitive dep of pre-commit, pinned to fix GHSA-94p9-xgh2-xp45, GHSA-9h9j-4vrj-gf7g,
  # GHSA-x78j-v8h9-3j2q, GHSA-p58f-9548-mpm2 (vulnerable < 21.7.13)
  virtualenv==21.14.5
  ```
  Пін закриває всі 4 advisory одночасно і робить версію однаковою локально й у CI.

### 3.4 Повторне сканування

| Скан | Компонентів | Critical | High | Medium | Low |
|---|---|---|---|---|---|
| `pip-audit -l` (`.venv` після `pip install -r requirements-dev.txt`) | 89 | 0 | 0 | 0 | 0 |
| `pip-audit -r requirements-dev.txt` (з доданими аналізаторами) | 86 | 0 | 0 | 0 | 0 |

Звіти: [`sca-after.txt`](lab3/reports/sca-after.txt), [`sca-after.json`](lab3/reports/sca-after.json). Працездатність після оновлення: `pytest` → **1269 passed** (unit + integration), `pre-commit run --all-files` працює з новим virtualenv.

### 3.5 Відтворюваність

- CI job `sca`: `pip install pip-audit==2.10.1 && pip-audit -r requirements-dev.txt --desc` — ненульовий exit code при будь-якій відомій вразливості валить пайплайн і блокує `build`/`publish`.
- Локально: `pip-audit -l` (див. demo-гайд).

## 4. Secrets Leak Prevention

### 4.1 Конфігурація

`.pre-commit-config.yaml` (секретів не містить):

```yaml
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1
    hooks:
      - id: gitleaks   # gitleaks git --pre-commit --redact --staged --verbose
```

- Hook сканує **staged changes** і повертає exit code 1 → `git commit` переривається.
- `pre-commit install` уже виконано (`.git/hooks/pre-commit`).
- CI job `secrets`: `gitleaks git --redact -v` по **всій історії** (`fetch-depth: 0`) — страхує від `git commit --no-verify` і від клонів, де hook не встановлено.
- `.gitleaksignore` — точкові винятки за fingerprint (коміт:файл:правило:рядок) з обґрунтуванням: два false positives (метадані вкладок IDE у вже видаленій з репо `.idea/`) і один прийнятий ризик (див. 4.4). Нові знахідки з тим самим значенням в інших місцях не ігноруються.

### 4.2 Краш-тест

`scripts/secrets_trap.py` генерує **синтетичний** токен формату Stripe test-key (`sk_test_` + 32 випадкові символи `secrets.choice`). Його не видавав жоден сервіс, він ні до чого не дає доступу і генерується заново при кожному запуску — тому в репозиторії (і в цьому звіті) немає жодного літерала, схожого на секрет.

1. `python scripts/secrets_trap.py plant` → `demo/payment_gateway.py` з `PAYMENT_GATEWAY_TOKEN = "sk_test_…"`.
2. `git add demo/` → `git commit` → **FAIL**:
   ```
   Detect hardcoded secrets.................................................Failed
   - hook id: gitleaks
   - exit code: 1
   Finding:     ...NT_GATEWAY_TOKEN = "REDACTED"
   RuleID:      stripe-access-token
   File:        demo/payment_gateway.py
   Line:        4
   WRN leaks found: 1
   ```
   Коміт не створено (`git log` не змінився).
3. `python scripts/secrets_trap.py fix` → значення переноситься в `.env`, код читає `os.getenv("PAYMENT_GATEWAY_TOKEN", "")`, у `.env.example` додається порожній ключ.
4. `git add demo/ .env.example` (перезаписує staged-версію з секретом — індекс очищено), `git diff --cached | grep sk_test` → порожньо → `git commit` → **PASS** (`Detect hardcoded secrets....Passed`).

### 4.3 Безпечна конфігурація проєкту

- Читання з Environment Variable — `src/fleet_management/config.py` (pydantic-settings читає env/`.env`): `jwt_secret_key: str | None = None`; у `docker-compose.yml` — `JWT_SECRET_KEY: ${JWT_SECRET_KEY:?...}` (без значення compose не стартує).
- `.gitignore` містить `.env`.
- `.env.example` — лише ключі без значень (`JWT_SECRET_KEY=`, `SONAR_TOKEN=`, `PAYMENT_GATEWAY_TOKEN=` після демо).

### 4.4 Аудит історії репозиторію

Повний скан історії (`gitleaks git`) знайшов 4 збіги:

| Правило | Файл | Коміт | Висновок |
|---|---|---|---|
| generic-api-key ×2 | `.idea/claudeCodeEditorTabs.xml` | 82cbc51 | False positive — id сесій/назви вкладок IDE. `.idea/` прибрано з репо в f08bb56. Додано у `.gitleaksignore` |
| sonar-api-token ×2 | `README.md` рядки 276, 284 | 4e159b8 | **Справжній токен локального SonarQube** (`localhost:9000`), закомічений до Lab 3 і пізніше замінений на `<твій токен>`. **Прийнятий ризик**: інстанс доступний лише на `localhost` машини розробника, ззовні токен непридатний; у поточному дереві замінений плейсхолдером. Переписування історії публічного `main` (force-push) визнано непропорційним для навчального проєкту. Fingerprint-и додано в `.gitleaksignore` з коментарем; компенсувальний контроль — hook + CI-скан не допускають нових витоків. Рекомендовано відкликати токен у SonarQube (My Account → Security → Revoke) |

## 5. Підсумкова таблиця

| Показник | Початковий стан | Контрольне порушення / ризик | Фінальний стан |
|---|---|---|---|
| Cognitive Complexity | 11 | Вкладеність + 8 `return` | **3** (≤ 15) |
| Cyclomatic Complexity | 11 (> 10, rank C) | Висока кількість шляхів | **3** (rank A), xenon gate PASS |
| Regression tests | PASS (1224) | Ризик зміни поведінки | **PASS** (1224 unit / 1269 total, golden master 1152 кейси) |
| Critical / High CVE | 0 / 3 (+1 Medium) у `.venv` | virtualenv 21.7.8 (transitive via pre-commit) | **0 / 0** — оновлено до 21.14.5 |
| Secret scan status | PASS | FAIL на синтетичному `sk_test_` (stripe-access-token) | **PASS** |
| Git repository state | Без секретів у робочому дереві | Коміт заблоковано | Без секретів; історичний локальний Sonar-токен — задокументований прийнятий ризик, повний скан історії PASS |
