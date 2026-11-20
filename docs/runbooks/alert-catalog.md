---
title: Каталог алертів моніторингу
owner: "@YakymivDanylo"
status: published
review_date: 2027-02-18
review_cycle_days: 90
tags: [ops]
---

# Каталог алертів моніторингу

Правило: **алерт без runbook — це шум**. Кожен алерт тут має умову, серйозність, відповідальну роль і runbook; кожен
тригер [[RB-001]] відповідає алерту з цього каталогу. Шкала серйозності — як у матриці інцидентів
[[maintenance-plan#матриця-ескалації|плану супроводу]]: SEV-1 — система недоступна/втрата даних, SEV-2 — деградація
ключової функції або порушення SLO, SEV-3 — ризик без впливу на користувача.

| ID | Назва | Умова спрацювання | Серйозність | Відповідальна роль | Runbook | Де реалізовано |
|---|---|---|---|---|---|---|
| ALR-01 | `FleetHighErrorRate` | `sum(rate(http_requests_total{status=~"5.."}[1m])) / sum(rate(http_requests_total[1m])) > 0.05` протягом 1 хв | SEV-2 | SRE on-call (L2) | [[isd#23-реліз-і-відкат\|ISD §2.3 відкат релізу]]; якщо зіпсовано дані — [[RB-001]] §Б | PrometheusRule у чарті (`charts/fleet-management/templates/prometheusrule.yaml`) |
| ALR-02 | `FleetDatabaseDown` | `GET /health` ≠ 200 на всіх репліках **або** `pg_isready` неуспішний ≥ 2 хв (у compose — healthcheck `db` = `unhealthy`) | SEV-1 | SRE on-call (L2) → власник БД (L3) | [[RB-001]] §Б | compose healthcheck `db`; правило Prometheus `probe_success{job="fleet-health"} == 0` — у плані супроводу |
| ALR-03 | `FleetBackupStale` | `python scripts/db_backup.py check --max-age-hours 26` повертає 1 (немає копії, SHA-256 не збігається або копія старша за 26 год) | SEV-3 | DevOps (L2) | [[RB-001]] §А | скрипт + cron хоста бекапів (щогодини) |
| ALR-04 | `FleetRestoreDrillFailed` | щомісячний `python scripts/db_backup.py drill` завершився `restore drill: FAIL` | SEV-2 | DevOps (L2) → власник БД (L3) | [[RB-001]] §В | скрипт; запуск — 1-й робочий день місяця |

**Порогові значення.** 5 % 5xx за 1 хв — той самий поріг, що й canary-аналіз Argo Rollouts (успішних ≥ 95 %),
щоб реліз і моніторинг мали одне визначення «погано». 26 год для копії = добовий розклад + 2 год запасу на тривалий
дамп. 2 хв для БД — щоб не будити людину через рестарт контейнера (≈ 10–20 с).

Пов'язано: [[RB-001]] · [[slo-policy]] · [[isd]] · #ops
