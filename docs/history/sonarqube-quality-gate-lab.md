> **DEPRECATED (2026-11-14, аудит документації ЛР№10).** Документ процесу: історичний звіт лабораторної
> роботи з SonarQube (вересень 2026), перенесений із README, бо описує стан коду на момент коміту
> `b6dde1c`…`b0063cf`, а не поточну систему. Не оновлюється. Актуальні гейти якості — [ISD §5](../isd.md#isd-cicd).

# Статичний аналіз якості коду (SonarQube) — звіт ЛР, вересень 2026

Локальний SonarQube Community Edition піднімається через Docker Compose:

```powershell
docker compose -f config/docker-compose.yml up -d sonarqube
```

Дашборд: http://localhost:9000 (проєкт `fleet-management`).

Токен сканера генерується один раз у `http://localhost:9000/account/security`.

Запуск сканування (вручну, коли потрібно перевірити поточний стан коду):

```powershell
docker run --rm `
    -e SONAR_HOST_URL="http://host.docker.internal:9000" `
    -e SONAR_TOKEN="<токен>" `
    -v "${PWD}:/usr/src" `
    -w /usr/src `
    sonarsource/sonar-scanner-cli
```

Результат — у Quality Gate на дашборді проєкту.

### Завд.1: Baseline Scan

Перше сканування (коміт `b6dde1c`, до інтеграції SonarQube і Quality Gate) зафіксувало такий стан кодової бази:

| Метрика | Значення |
|---|---|
| Bugs | 0 |
| Vulnerabilities | 0 |
| Security Hotspots | 0 |
| Code Smells | 6 |
| Technical Debt (sqale_index) | 30 хв |
| Duplicated Lines % | 0.0% |
| Cyclomatic Complexity (проєкт) | 34 |
| Cognitive Complexity (проєкт) | 10 |
| Test Coverage | 0.0% (тестів ще немає) |
| Lines of Code (ncloc) | 332 |
| **Quality Gate** | **PASS** (стандартний профіль `Sonar way`) |

Повторне сканування (тривіальна зміна — форматування `config.py`) підтвердило, що аналізатор коректно перераховує метрики без ручного втручання: значення не змінились (немає нового коду), Quality Gate лишився PASS.

### Quality Gate: критерії та обґрунтування

Проєкту прив'язано кастомний профіль `Fleet Management Custom Gate` (відмінний від стандартного `Sonar way`), з 4 обов'язковими критеріями:

| # | Критерій | Категорія | Поріг |
|---|---|---|---|
| 1 | New Bugs | New Code, Reliability | = 0 |
| 2 | New Security Hotspots Reviewed | New Code, Security | = 100% |
| 3 | Duplicated Lines % | Overall Code, Duplication | ≤ 3% |
| 4 | Maintainability Rating | Overall Code, Maintainability | = A |

Архітектурне обґрунтування (під стек FastAPI + async SQLAlchemy + PostgreSQL):

1. **New Bugs = 0** — async I/O (await/coroutines, спільний стан по кількох воркерах) — типове джерело нових багів (unawaited coroutine, race condition). Блокує їх на вході, а не після мержу.
2. **New Security Hotspots Reviewed = 100%** — застосунок ходить у PostgreSQL напряму (`text()` для raw SQL вже є в `main.py`) — SQL injection головний ризик. Кожен hotspot має пройти ручний рев'ю перед мержем.
3. **Duplicated Lines % ≤ 3%** — шарова CRUD-архітектура (models/schemas/services/api на кожну сутність: Vehicle, Station, Renter, Rental) природньо тягне copy-paste між сутностями. Ліміт стримує це змасштабуванням проєкту.
4. **Maintainability Rating = A** — бізнес-правила живуть у `services/` (розрахунок вартості оренди, перевірка доступності авто/місця, право на оренду). Саме такі функції найшвидше обростають вкладеними умовами під нові edge-cases. Первісно критерій був заданий як `Cognitive Complexity (Overall) ≤ 15`, але ця метрика — сира сума складності по всьому проєкту, тому механічно росте з кожним новим (навіть простим) методом і не відображає реальну якість. Замінено на `Maintainability Rating = A` — нормалізований показник (співвідношення технічного боргу до розміру коду), а per-method ліміт ≤15 і далі контролює правило аналізатора `S3776`.

### Завд.3: симуляція деградації якості та відновлення

Коміт `fe9cee2` навмисно вносить у робочу гілку **2 незалежні порушення**, кожне ціляє в окремий критерій Quality Gate:

**Порушення 1 — дублювання (Overall Code, Duplicated Lines % ≤ 3%).** Файл `src/fleet_management/api/vehicles.py` (39 рядків) скопійовано без жодної зміни під назвою `api/fleet_vehicles.py`:

```python
# src/fleet_management/api/fleet_vehicles.py — точна копія vehicles.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Vehicle
from ..schemas import VehicleCreate, VehicleRead
from ..services import station_service

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.post("", response_model=VehicleRead, status_code=201)
async def create_vehicle(
    payload: VehicleCreate, db: AsyncSession = Depends(get_db)
): ...  # тіло функції ідентичне оригіналу
```

**Порушення 2 — критична Cognitive Complexity (Overall Code).** У `services/rental_service.py` додано `calculate_discount` з 4 рівнями вкладених `if/else` (без Guard Clauses):

```python
def calculate_discount(
    rental_count, is_vip, vehicle_type, station_zones, has_coupon, is_weekend, is_holiday
):
    discount = 0.0
    if is_vip:
        if rental_count > 10:
            if vehicle_type == "premium":
                discount += 5
            else:
                discount += 10
        else:
            if vehicle_type == "premium":
                discount += 2
            else:
                discount += 5
    else:
        if rental_count > 20:
            discount += 3
        elif rental_count > 5:
            if has_coupon:
                discount += 4
            else:
                discount += 1
    if is_weekend:
        for zone in station_zones:
            if zone == "center":
                discount += 1
            elif zone == "suburb":
                discount -= 1
    if is_holiday:
        if has_coupon:
            discount += 2
        else:
            discount += 1
    return discount
```

**Результат сканування — Quality Gate: FAIL.** Аналізатор чітко вказав 4 умови, що впали:

| Метрика | Поріг | Факт |
|---|---|---|
| Duplicated Lines % (New Code) | ≤ 3% | 44.8% |
| Duplicated Lines % (Overall) | ≤ 3% | 13.6% |
| Cognitive Complexity `calculate_discount` | ≤ 15 | **31** (правило `python:S3776`) |
| New Issues | = 0 | 2 нових issue |

**Рефакторинг (коміт `b296f22`)** — не видалення, а виправлення:
- `fleet_vehicles.py` видалено — файл ніде не підключався до застосунку, чистий copy-paste-сміттяр без функціональної цінності.
- `calculate_discount` розкладено на `_vip_discount`, `_regular_discount`, `_weekend_zone_discount`, `_holiday_discount` (Extract Method) — кожна функція тривіальна, Cognitive Complexity кожної <5.

Поведінка після рефакторингу верифікована на 1152 комбінаціях вхідних параметрів — 0 розбіжностей зі старою версією, перш ніж стару логіку видалено.

**Фінальне сканування — Quality Gate: PASS.** Duplicated Lines % = 0.0%, 0 залишкових issues по складності.

**Порівняльна таблиця (за формою методички):**

| Показник якості | Baseline | Failed | Fixed |
|---|---|---|---|
| Bugs (кількість) | 0 | 0 | 0 |
| Vulnerabilities / Hotspots | 0 / 0 | 0 / 0 | 0 / 0 |
| Code Smells (кількість) | 6 | 8 | 6 |
| Technical Debt (у хвилинах) | 30 | 56 | 30 |
| Duplicated Lines % | 0.0% | 13.6% | 0.0% |
| Cognitive Complexity (найгірший метод) | <15 (issues немає) | **31** (`calculate_discount`) | <15 (issues немає) |
| Quality Gate Status | PASS | **FAIL** | PASS |

### Завд.4: рефакторинг найгірших методів (Maintainability / Technical Debt)

Ідентифіковано через звіт аналізатора (правило `S3776`, сортування по `sqale_index`) два методи з найгіршими показниками:

| Метод | Файл | Cognitive Complexity (До → Після) | Technical Debt (До → Після) |
|---|---|---|---|
| `validate_rental_eligibility` | `services/rental_service.py` | **58 → 8** (критичний рівень) | 48 хв → 0 |
| `rentals_summary` | `api/rentals.py` | **19 → ~4** | 9 хв → 0 |

Після рефакторингу: 0 залишкових порушень `S3776`, `code_smells` та `sqale_index` (Technical Debt) проєкту повернулись до рівня Baseline.

**Застосовані техніки:**
- **Guard Clauses** — у `validate_rental_eligibility` прибрано 4 рівні вкладеного `if/else`, кожна умова виходу тепер на верхньому рівні.
- **Extract Variable** — повторювана умова "потрібна застава на вихідних" рахувалась двічі в різних гілках; винесена в одну змінну `deposit_missing`.
- **Делегування сервісу замість дублювання** — `rentals_summary` дублював формулу розрахунку вартості з `calculate_cost`; замінено прямим викликом сервісу (усунуто і складність, і порушення шарової архітектури).
- **Extract Method через `Counter`** — ручний цикл з `if/elif` для підрахунку оренд за статусами замінено на `collections.Counter`.

Всі рефакторинги верифіковано на еквівалентність поведінки: `validate_rental_eligibility` — 1152 комбінації вхідних параметрів, `calculate_cost`-делегування — 1000 значень тривалості, розбіжностей 0.

**Git-історія кейсу (До/Після для Code Review):**
- `1cb64a7` — навмисно нерефакторений код (До)
- `b0063cf` — рефакторинг (Після)

**Порівняльна таблиця станів проєкту (Завд.3 + Завд.4):**

| Показник | Baseline | Failed (Завд.3) | Fixed (Завд.3) | Fixed (Завд.4) |
|---|---|---|---|---|
| Bugs | 0 | 0 | 0 | 0 |
| Code Smells | 6 | 8 | 6 | 6 |
| Duplicated Lines % | 0.0% | 13.6% | 0.0% | 0.0% |
| Technical Debt (sqale_index) | 30 хв | 56 хв | 30 хв | 97 хв → 30 хв |
| Quality Gate | PASS | **FAIL** | PASS | PASS |

## Висновок: Cyclomatic vs Cognitive Complexity

**Cyclomatic Complexity** рахує кількість незалежних шляхів виконання через код (кожен `if`, `for`, `while`, `case` додає +1 незалежно від рівня вкладеності). Вона добре відповідає на питання "скільки тестів потрібно для 100% покриття гілок", але не розрізняє плаский код (10 послідовних `if` на одному рівні) і глибоко вкладений (той самий `if` в `if` в `if`).

**Cognitive Complexity** штрафує саме за вкладеність: кожен додатковий рівень вкладеної умови множить "вартість" наступної умови. У нашому кейсі це видно напряму на `validate_rental_eligibility` — Cyclomatic Complexity була відносно помірною (кожен `if` рахувався один раз), але Cognitive Complexity сягнула **58** через 7 рівнів вкладеності. Функція з тим самим набором умов, але без вкладеності (Guard Clauses), впала до Cognitive Complexity ~8 — при цьому Cyclomatic Complexity змінилась значно менше, бо кількість гілок рішень залишилась приблизно тією ж.

Висновок: Cyclomatic Complexity важлива для тестування (скільки шляхів треба покрити), а Cognitive Complexity — для читабельності та супроводжуваності (наскільки важко людині утримати логіку в голові). Для code review і рефакторингу Cognitive Complexity інформативніша, бо саме вона прогнозує, скільки часу піде на розуміння і безпечну зміну коду.

**Доцільність автоматичного контролю технічного боргу на комерційних проєктах:** ручний код-рев'ю фізично не встигає відстежувати деградацію якості на кожному PR, особливо коли команда велика і дедлайни тиснуть (як і сталось з `validate_rental_eligibility` та `rentals_summary` — реалістичний сценарій "написано під тиском, рефакторинг відклали"). Quality Gate з розділенням New Code / Overall Code дозволяє блокувати регрес нового коду негайно, не вимагаючи одноразового "великого рефакторингу" всього legacy — технічний борг контролюється інкрементально, на кожному коміті, автоматично і без суб'єктивності ручного рев'ю.
