---
title: Стандарти коду
owner: "@YakymivDanylo"
status: published
review_date: 2027-02-18
review_cycle_days: 90
tags: [ops]
---

# Стандарти коду (ЛР№1 + гейти якості)

Правила записані **в конфігурації**, а не лише в цьому тексті: сторінка пояснює, *де* живе правило і *чому* воно таке.

| Правило | Значення | Джерело істини | Де перевіряється |
|---|---|---|---|
| Стиль і імпорти | ruff: `E`, `F`, `I`, `UP`, `B`; довжина рядка 100; `target-version = py313` | `pyproject.toml` → `[tool.ruff]` | pre-commit, `CI` → `lint` |
| Форматування | `ruff format` | `pyproject.toml` | pre-commit, `CI` → `lint` |
| Шари | `api/` (HTTP) → `services/` (бізнес-правила) → `models/` (ORM); `schemas.py` — Pydantic-контракти | [[sdd#c-api\|SDD §3.2]] | рев'ю |
| Цикломатична складність | ≤ 10 на блок (xenon rank B) | `.github/workflows/ci.yml` → `complexity` | pre-commit `complexity-gate`, CI |
| Когнітивна складність | ≤ 15 на функцію (complexipy) | там само | CI |
| Тести | Line Coverage ≥ 90 % **AND** Mutation Score ≥ 75 % | `scripts/quality_gate.py` | `CI` → `quality-gate` |
| Секрети | жодного секрету в Git | `.gitleaksignore`, pre-commit gitleaks | `CI` → `secrets` |
| Кодування файлів | UTF-8 без BOM, LF | `.pre-commit-config.yaml`, `.gitattributes` | pre-commit |
| Docstrings | Google style для публічних функцій сервісів і телеметрії | — | рендеряться в [[python-reference]] |
| Документація | Markdown, front matter-паспорт, wikilinks | `.markdownlint-cli2.yaml`, `mkdocs.yml` | конвеєр `Docs` |

## Гілки та коміти

- Гілки: `feat/<slug>`, `fix/<slug>`; `main` захищена.
- Conventional Commits; області (scope): `api`, `ui`, `db`, `auth`, `core`, `infra`, `docs`, `ci`.
- Повідомлення коміту описує лише зміну.

Пов'язано: [[CONTRIBUTING]] · [[local-setup]] · #ops
