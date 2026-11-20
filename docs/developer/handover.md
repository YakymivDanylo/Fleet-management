---
title: Пакет передачі знань (Handover)
owner: "@YakymivDanylo"
status: published
review_date: 2027-02-18
review_cycle_days: 90
tags: [ops]
---

# Пакет передачі знань (Handover Package)

Для умовної команди супроводу, яка приймає систему від автора. Стан на коміт `859860e` (2026-11-14).

## 1. Реєстр документів паспорта

| Документ | Що відповідає | Власник | Цикл | Остання перевірка | Статус актуальності |
|---|---|---|---|---|---|
| [README.md](https://github.com/YakymivDanylo/Fleet-management/blob/main/README.md) | що це, швидкий старт, тести | Danylo Yakymiv | 90 д | 2026-11-14 | ✅ PASS |
| [docs/sdd.md](../architecture/sdd.md) | компоненти, C4, модель даних, API | Danylo Yakymiv | 180 д | 2026-11-14 | ✅ PASS |
| [docs/isd.md](../architecture/isd.md) | середовища, порядок старту, CI/CD, моніторинг, бекап RTO/RPO | Danylo Yakymiv | 90 д | 2026-11-14 | ✅ PASS |
| [ADR-0001](../architecture/adr/adr-0001-postgresql-redis-rabbitmq-storage.md) | чому PostgreSQL + Redis + RabbitMQ | Danylo Yakymiv | 180 д | 2026-11-14 | ✅ Accepted |
| [ADR-0002](../architecture/adr/adr-0002-gitops-argo-canary-delivery.md) | чому GitOps + canary з авто-відкатом | Danylo Yakymiv | 180 д | 2026-11-14 | ✅ Accepted |
| [[CONTRIBUTING\|CONTRIBUTING / DoD]] | регламент, «зміна коду = зміна документації» | Danylo Yakymiv | 90 д | 2026-11-14 | ✅ PASS |
| [charts/fleet-management/README.md](https://github.com/YakymivDanylo/Fleet-management/blob/main/charts/fleet-management/README.md) | параметри Helm-чарта | Danylo Yakymiv | 90 д | 2026-11-14 | ✅ PASS |
| [CHANGELOG.md](https://github.com/YakymivDanylo/Fleet-management/blob/main/CHANGELOG.md) | історія змін для бізнесу | автор PR | кожен PR | 2026-11-14 | ✅ PASS |
| [[k8s-raw-manifests\|k8s/ (сирі маніфести)]] | — | — | — | 2026-11-14 | ⚠️ deprecated, не використовувати |

Актуальність перевіряється автоматично: `python scripts/doc_audit.py --strict` (CI-job `docs-currency`).

## 2. Онбординг нового розробника (від README до локального запуску)

1. **Прочитати** [README](https://github.com/YakymivDanylo/Fleet-management/blob/main/README.md) (призначення, аудиторії) і [SDD §2–3](../architecture/sdd.md#2-c4--контекст-і-контейнери) —
   15 хв: зрозуміти 7 контейнерів і шари `api/ → services/ → models/`.
2. **Підготувати середовище:** Docker Desktop, Git, Python 3.13; `git clone`, `Copy-Item .env.sandbox.example .env.sandbox`,
   згенерувати `JWT_SECRET_KEY` (команда в README).
3. **Запустити:** `docker compose -p fleet_sandbox --env-file .env.sandbox up -d --build`; дочекатися `healthy`
   ([порядок старту — ISD §2.1](../architecture/isd.md#isd-startup-order)); перевірити `GET /health`, відкрити `/app/` і `/docs`;
   створити адміна `create-admin`.
4. **Прогнати тести:** тимчасові Postgres/Redis на `55432`/`56379` + `pytest tests -v` (README, «Тести та лінтер»);
   встановити `pre-commit install` — ті самі гейти, що в CI.
5. **Перша зміна:** гілка `feat/<slug>`, PR за шаблоном (чекбокс документації), `python scripts/doc_audit.py --strict`
   перед push.

## 3. Декларація Bus Factor

Метод: `git log --format='%aN' -- <компонент> | sort | uniq -c` (сирий вивід — звіт ЛР№10, гілка `feat/lab9-lab10-quality`).
Ідентичності `YakymivDanylo` і `Danylo Yakymiv` — одна людина.

| Компонент | Комітів | Авторів | Bus Factor | Ризик втрати знань | «Темна зона» (що не очевидно з коду) |
|---|---|---|---|---|---|
| `services/rental_service.py` (оренда, вартість, знижки, eligibility) | 8 | 1 | **1** | 🔴 високий | бізнес-правила знижок і застави; відсутність `FOR UPDATE` при старті оренди (SDD §4) |
| `privacy/`, GDPR-сервіси | 2 + сервіси | 1 | **1** | 🔴 високий | правові підстави, версії політики згод, що саме анонімізується |
| `charts/`, `argocd-apps/` (GitOps, canary, аналіз) | 20 / 6 | 1 | **1** | 🔴 високий | ручний Secret `fleet-secret`, порядок CRD Rollouts, пороги аналізу 95 % |
| `.github/workflows/` (10 гейтів) | 16 | 1 | **1** | 🟠 середній | чому саме пороги coverage 90 / mutation 75 / CC 10; пінований `Dockerfile.metrics` |
| `telemetry/` (worker) | 4 | 1 | **1** | 🟠 середній | ідемпотентність за `(vehicle_id, recorded_at)`, правило «новіший стан» у Redis |
| `resilience.py`, `cache.py` | 2 | 1 | **1** | 🟠 середній | таймаути 200 мс / 3 спроби підібрані навантажувальним тестом |
| `security.py` (Argon2 у пулі потоків) | 3 | 1 | **1** | 🟡 низький | `PASSWORD_HASH_WORKERS` — причина в звіті навантаження (event loop блокувався) |
| `api/`, `alembic/versions`, `nginx/`, `loadtest/` | 16 / 5 / 1 / 9 | 1 | **1** | 🟡 низький | добре покрито SDD/ISD і тестами |

**Висновок:** Bus Factor системи = **1** — кожен компонент створила й розуміє одна людина (single point of knowledge).

### План усунення single points of knowledge

| # | Захід | Компоненти | Критерій виконання |
|---|---|---|---|
| 1 | **Парне володіння:** призначити co-owner для кожного рядка реєстру `CONTRIBUTING.md`; кожен PR у «червоні» компоненти — рев'ю co-owner'а | rental, privacy, GitOps | у таблиці §3 `CONTRIBUTING.md` 2 власники на документ; ≥ 2 автори в `git shortlog` за квартал |
| 2 | **Документування темних зон:** ADR-0003 «Конкурентний старт оренди» (FOR UPDATE vs optimistic lock); ADR-0004 «Політика згод і анонімізації» | rental, privacy | ADR у статусі Accepted |
| 3 | **Runbook ручних кроків:** створення `fleet-secret`, відновлення з бекапу (ISD §7) — co-owner виконує сам, без автора | GitOps, PostgreSQL | успішне тестове відновлення в sandbox, проведене не автором |
| 4 | **Ротація чергування:** другий інженер реагує на алерт 5xx > 5 % і на abort canary | моніторинг | ≥ 1 розібраний інцидент |
| 5 | **Метрика контролю:** `git shortlog -sn --since=90.days -- <компонент>` у квартальному перегляді регламенту | усі | Bus Factor ≥ 2 для «червоних» компонентів |

## 4. Вердикт «Always Ready to Handover»

| Критерій | Стан |
|---|---|
| Документація паспорта повна (README, SDD, ISD, ADR, регламент) і актуальна | ✅ `doc_audit --strict` PASS |
| Новачок запускає систему за README без автора | ✅ 5 кроків, усі команди в репозиторії |
| Розгортання, відкат і бекап описані та перевірені | ✅ ISD §2.3, §7 (pg_dump/pg_restore перевірено 2026-11-14) |
| Регламент і автоматичний контроль дрейфу | ✅ `docs-currency` у CI, PR-шаблон |
| Знання розподілені між ≥ 2 людьми | ❌ Bus Factor = 1 |

**Вердикт:** система **документаційно готова до передачі** (Ready to Handover за артефактами), але **не в стані
«Always Ready to Handover»** організаційно: поки Bus Factor = 1, неявні знання про «темні зони» (таблиця §3)
зосереджені в одній людині. Стан досягається після заходів 1–3 плану (co-owner + 2 ADR + runbook, виконаний не автором).

Пов'язано: [[sdd]] · [[isd]] · [[CONTRIBUTING]] · [[local-setup]] · #ops
