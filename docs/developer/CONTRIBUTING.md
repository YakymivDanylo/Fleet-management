---
title: CONTRIBUTING — як вносити зміни
owner: "@YakymivDanylo"
status: published
review_date: 2027-02-18
review_cycle_days: 90
tags: [ops]
---

# CONTRIBUTING — як вносити зміни

Перед першою зміною: [[local-setup|підготувати середовище]] і прочитати [[code-standards|стандарти коду]].

## Процес

1. Гілка від `main`: `feat/<slug>` або `fix/<slug>`; у `main` напряму не комітимо.
2. Коміти — Conventional Commits (`feat(api): …`, `fix(core): …`, `docs(api): …`, `ci(docs): …`), один коміт —
   одна логічна зміна.
3. Pull request за шаблоном `.github/pull_request_template.md`.
4. Рев'ю власника: `.github/CODEOWNERS` призначає обов'язкових рев'юерів; для `docs/`, `mkdocs.yml` і
   `docs/api/openapi.yaml` — власник документації. З увімкненим branch protection «Require review from Code
   Owners» зміна документа без його схвалення фізично не зливається.
5. Зелені перевірки: `CI` (код) і `Docs` (документація, `.github/workflows/docs.yml`).

## Definition of Done (docs-or-don't-merge)

Pull request, що **змінює публічну поведінку** — новий чи змінений ендпоінт, формат відповіді, код помилки,
змінна оточення чи конфігурація, контракт телеметрії, — **не зливається**, доки в тому ж PR не виконано:

- [ ] `docs/api/openapi.yaml` оновлено (нові шляхи, схеми, приклади, коди помилок); `info.version` підвищено за SemVer:
      MINOR — additive, MAJOR — breaking (+ міграційний гайд у [[api-overview]]);
- [ ] Spectral: `npx @stoplight/spectral-cli@6.17.1 lint docs/api/openapi.yaml` — 0 errors;
- [ ] contract-тест Schemathesis проти запущеного API — без розбіжностей ([[contract-testing]]);
- [ ] зачеплені сторінки `docs/` оновлено: SDD (компоненти, модель даних, інвентар маршрутів), ISD (розгортання,
      змінні, CI/CD), runbook-и й алерти ([[alert-catalog|каталог алертів]]), новий ADR для
      архітектурного рішення (старий → `Superseded`);
- [ ] у кожній зміненій сторінці оновлено front matter: `owner`, `status`, `review_date`;
- [ ] запис у `CHANGELOG.md`;
- [ ] `markdownlint-cli2` і `mkdocs build --strict` — зелені (локально або стадії `lint` / `build` конвеєра `Docs`).

Якщо документацію оновлювати не потрібно (рефакторинг без зміни поведінки), автор PR пише причину в
шаблоні — рев'юер-власник погоджує або відхиляє.

### Документаційні перевірки, що автоматизують DoD

| Що перевіряється | Інструмент | Де | Поріг |
|---|---|---|---|
| Контракт API | Spectral (`.spectral.yaml`) | job `api-contract` | 0 errors |
| Розмітка | markdownlint-cli2 (`.markdownlint-cli2.yaml`) | job `lint` | 0 порушень |
| Посилання, навігація, якорі, wikilinks | `mkdocs build --strict` | job `build` | 0 warnings (інакше Exit Code 1) |
| Актуальність | `scripts/docs_review_audit.py` (`review_date` з front matter) | job `review-audit` | 0 прострочених `published`-сторінок |
| Дрейф коду й документації | `scripts/doc_audit.py --strict` (ЛР№10) | `CI` → `docs-currency` | усі маршрути в SDD, drift ≤ 20 комітів |

## Супровід документації

- **Цикли перегляду** (з аудиту ЛР№10): експлуатаційні сторінки — 90 днів, архітектурні — 180 днів,
  ADR — лише статус. `review_date` = дата перегляду + цикл.
- **Прострочено** (`review_date` < сьогодні): власник переглядає сторінку → оновлює зміст і `review_date`,
  або переводить у `status: deprecated` з полем `superseded_by` і банером-переспрямуванням. Застарілі сторінки
  **не видаляються** — історія лишається в навігації в розділах «Архів».
- **Версії документації**: мажорна зміна бази знань фіксується тегом `docs-vN.0`
  (`git tag -a docs-v1.0 -m "…" && git push origin docs-v1.0`); знімок відновлюється так само, як код релізу:
  `git checkout docs-v1.0 && mkdocs build --strict`.
- **ADR незмінні**: рішення не переписується; нове рішення — новий номер, старе отримує `Superseded by ADR-NNNN`
  ([кущ ADR](../architecture/adr/index.md)).

Пов'язано: [[handover]] · [[documentation-regime]] (попередній регламент, deprecated) · #ops
