---
title: Fleet Management — база знань
owner: "@YakymivDanylo"
status: published
review_date: 2027-02-18
review_cycle_days: 90
tags: [ops]
---

# Fleet Management — база знань (Documentation as Code)

Бекенд і вебінтерфейс **станційного каршерінгу** з IoT-телеметрією. Як запустити систему за 5 хвилин —
у кореневому [README репозиторію](https://github.com/YakymivDanylo/Fleet-management#readme)
(рівень 1 піраміди). Цей сайт зібраний з каталогу `docs/` командою `mkdocs build --strict` і публікується
на GitHub Pages конвеєром `.github/workflows/docs.yml`: документ, що не збирається, не публікується.

## Піраміда документації

| Рівень | Питання аудиторії | Аудиторія | Розділ |
|---|---|---|---|
| 1 · README | Що це і як запустити? | усі, бізнес | `README.md` у корені репозиторію |
| 2 · Developer Docs | Як приєднатися до розробки? | новий розробник | [[developer-index\|Developer Docs]] |
| 3 · API Docs | Як інтегруватися? | інтегратор, QA | [[api-overview\|API Docs]] |
| 4 · Architecture Docs | Чому система влаштована саме так? | архітектор, DevOps | [[architecture-index\|Architecture Docs]] |

Кожен факт живе **в одному місці**: формати відповідей API — лише в `openapi.yaml`, топологія і RTO/RPO —
лише в [[isd|ISD]], компоненти і модель даних — лише в [[sdd|SDD]], обґрунтування — лише в ADR.
Інші сторінки на ці факти посилаються, а не копіюють їх.

## Паспорт документа

Кожна сторінка має front matter: `owner` (власник актуальності), `status`
(`draft` / `in-review` / `published` / `deprecated`), `review_date` (дата наступного обов'язкового перегляду).
Прострочені `review_date` щодня показує CI-стадія `review-audit` — див. [[CONTRIBUTING#definition-of-done-docs-or-dont-merge|Definition of Done]].
Сторінки за темами — у [покажчику тегів](tags.md).
