---
title: ADR-0004
owner: "@YakymivDanylo"
status: published
adr_status: Accepted
decision_date: 2026-11-20
review_date: 2027-05-19
review_cycle_days: 180
tags: [architecture, adr, api]
---

# ADR-0004: Documentation as Code — MkDocs Material, API-first OpenAPI і strict-конвеєр з публікацією на GitHub Pages

- **Статус:** Accepted (замінює [[adr-0003-plain-markdown-doc-passport|ADR-0003]])
- **Дата рішення:** 2026-11-20 (ЛР№11)
- **Автор / власник:** Danylo Yakymiv
- **Пов'язані документи:** [[CONTRIBUTING]], [[api-overview]], [[isd#isd-cicd|ISD §5]]

## Контекст

Паспорт ЛР№10 ([[adr-0003-plain-markdown-doc-passport|ADR-0003]]) не має навігації та публічного сайту, а формати
відповідей API описані текстом у SDD і в автогенерованому FastAPI-OpenAPI — два джерела, які можуть розійтися.
Дефекти документації (мертве посилання, сторінка поза навігацією, зламаний блок коду) не зупиняють доставку.

## Розглянуті альтернативи

| # | Варіант | Плюси | Мінуси |
|---|---|---|---|
| A | **MkDocs Material + `openapi.yaml` (API-first) + GitHub Actions `--strict` + Pages** (обрано) | Markdown лишається вихідним форматом (Obsidian, GitHub); strict перетворює попередження на Exit Code 1; Swagger UI рендериться з того самого файлу | ручне ведення контракту; потрібен contract-тест проти коду |
| B | Sphinx + reStructuredText | autodoc «з коробки» | інший синтаксис, Obsidian не читає RST |
| C | Docusaurus | версіонування документації | Node/React-стек, чужий для Python-команди |
| D | Code-first: публікувати FastAPI `/openapi.json` | нуль ручної роботи | контракт = те, що випадково написано в коді; немає узгодженої схеми помилок і прикладів; у production вимкнено |

## Рішення

- Вихідний формат — Markdown у `docs/` з front matter `owner` / `status` / `review_date`, wikilinks Obsidian
  перетворює хук `docs_hooks/wikilinks.py`.
- Контракт HTTP API — `docs/api/openapi.yaml` (OpenAPI 3.1, SemVer у `info.version`), лінтинг Spectral, довідка
  рендериться з файлу плагіном `mkdocs-swagger-ui-tag`; відповідність коду перевіряє Schemathesis.
- Конвеєр `.github/workflows/docs.yml`: markdownlint → Spectral → `mkdocs build --strict` → GitHub Pages;
  аудит `review_date`.
- Рев'ю власника документів — `.github/CODEOWNERS`.

## Наслідки

- ✅ Дефект документації зупиняє публікацію так само, як червоний тест — реліз.
- ✅ Довідка API не може розійтися з контрактом: її генерує браузер з того самого `openapi.yaml`.
- ⚠️ Контракт треба оновлювати руками в тому ж PR, що й код (DoD); дрейф ловить лише contract-тест.
- ⚠️ Нові залежності збірки (`requirements-docs.txt`, Node для лінтерів) — версії зафіксовано.
