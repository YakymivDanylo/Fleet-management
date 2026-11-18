# Лабораторна робота №8 — CK & MOOD аудит, God Object, Inheritance Hell

Гілка: `feat/lab8-quality-engineering`. Інструменти: `scripts/ck_metrics.py` (AST-аналізатор CK/Lorenz-Kidd/MOOD),
`scripts/sonar_api.py` (клієнт SonarQube/SonarCloud Web API). Сирі дані — `docs/lab8/evidence/`.

## Важливе застереження щодо SonarQube

Python-аналізатор SonarQube **не має** метрик `class_complexity`, `coupling_between_objects`, `lcom4`, `dit`
(вони існують лише в Java-світі/плагінах). Тому `api/measures/component` для Python повертає лише
`complexity`, `cognitive_complexity`, `ncloc`, `functions`, `classes` (див. `scripts/sonar_api.py`).
CK/MOOD-значення отримано `scripts/ck_metrics.py`, який віддає JSON тієї ж форми, що й
`api/measures/component` (`component.measures[{metric,value}]`). SonarQube-сервер у цій сесії не запускався,
скріншотів немає — їх треба зробити окремо (Sonar-дашборд, `git log --graph`).

Визначення метрик — у docstring `scripts/ck_metrics.py`. Головне: DIT рахується від `object` (звичайний клас = 1);
LCOM = Henderson-Sellers LCOM* ∈ [0,1] (0 — ідеал), LCOM4 = число компонент зв'язності графа методів.

## Завдання 1 — базова лінія (ЛР№6: Core / Infrastructure / DTO)

```
python scripts/ck_metrics.py component src/fleet_management/services/rental_service.py
python scripts/ck_metrics.py component src/fleet_management/resilience.py
python scripts/ck_metrics.py component src/fleet_management/schemas.py
python scripts/ck_metrics.py mood src/fleet_management        # CK_EXCLUDE=lab8 — без піщочниці
```

| Файл (роль) | WMC | CBO | LCOM4 | LCOM | RFC | DIT |
|---|---|---|---|---|---|---|
| `services/rental_service.py` (Core Domain) | 28 | 14 | 10 | 0.86 | 34 | 1 |
| `resilience.py` (Infrastructure) | 11 | 5 | 1 | 0.50 | 9 | 2 |
| `schemas.py` (Utility/DTO, 15 класів) | 0 | 3 | 0 | 0.00 | 0 | 2 |

MOOD (79 класів): **MHF 15.8 %, AHF 4.7 %, COF 0.65 %** (40 пар зв'язків).

Вердикт: класів-мутантів у реальному коді немає (макс. CBO = 14 < 15, і це модуль вільних функцій, а не клас).
Домен — набір функцій без класів, тому `rental_service.py` має високий LCOM4 (10 незалежних функцій), що тут
свідчить про процедурний стиль, а не про God Object. COF низький (слабке зачеплення), але AHF 4.7 % — майже всі
поля публічні (Pydantic/ORM-моделі). Для завдань 2–3 застосовано «метод штучної агрегації» (пісочниця
`src/fleet_management/lab8/`).

## Завдання 2 — God Object

Мутант `RentalManager` (життєвий цикл + білінг + сповіщення + звіти):
**WMC 23, CBO 16, RFC 49, LCOM 0.59**; з матриці зв'язності (`evidence/baseline/coupling_matrix.md`) він має
13 вихідних зв'язків і 0 вхідних.

FAIL (`evidence/task2_fail/`): зміна сигнатур `StationRegistry.has_free_slot(+vehicle_type)` і
`TariffCalculator.price(+zone)` ламає 5 з 10 тестів `TypeError`; правити довелося б 3 місця в одному класі
(`end_rental`, `quote`, `build_invoice` та все, що через нього викликається) — Shotgun Surgery.

PASS: розбито на 4 класи за SRP, зв'язок лише через `Protocol`-контракти (`contracts.py`) та конструктор,
композиційний корінь — `wiring.py`:

| Клас | CBO | LCOM | LCOM4 | WMC |
|---|---|---|---|---|
| `RentalLifecycleService` | 8 | 0.20 | 1 | 5 |
| `BillingService` | 5 | 0.00 | 1 | 5 |
| `NotificationService` | 4 | 0.00 | 1 | 5 |
| `ReportingService` | 6 | 0.12 | 1 | 10 |

Тепер зміна сигнатури тарифу/станції зачіпає один шов (`BillingService._invoice`, `lifecycle.end_rental`).
Межа задачі CBO ≤ 8 та LCOM ≤ 0.2 виконана (в `RentalLifecycleService` CBO = 8 і LCOM = 0.2 — рівно на межі).

## Завдання 3 — Inheritance Hell

Baseline: `BasePricing → WeekendPricing → CorporatePricing`; листок: **DIT 3, PIM 21, NMO 7**, нових методів 4.

FAIL (`evidence/task3_fail/`): додано параметр `zone` лише в `BasePricing.base_rate`; 4 тести нащадків падають
(`TypeError` у `WeekendPricing.base_rate` та `CorporatePricing.subtotal`), базовий клас зелений.

PASS: `extends` прибрано. `WeekendPricing(base)` і `CorporatePricing(weekend, contract)` отримують попередній
шар через конструктор і делегують йому виклики.

| Клас | DIT | Overridden | PIM |
|---|---|---|---|
| `BasePricing` | 1 | 0 | 13 |
| `WeekendPricing` | 1 | 0 | 10 |
| `CorporatePricing` | 1 | 0 | 9 |

Зона (`zone`) тепер проходить через усі шари без правок у «нащадках» — тест
`test_airport_zone_is_forwarded_through_every_layer`.

## Git-історія

```
git log --oneline --graph feat/lab8-quality-engineering
chore(core): capture lab8 object-design baseline and metrics tooling   # Baseline
arch(audit): capture god object coupling failure, FAIL
refactor(audit): eliminate god object via interface decomposition, PASS
arch(audit): capture inheritance fragility crash, FAIL
refactor(audit): replace inheritance with composition pattern, PASS
```

Повний `tests/unit`: 1338 passed.
