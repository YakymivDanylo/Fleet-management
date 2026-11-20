---
title: Сирі маніфести k8s/ — deprecated
owner: "@YakymivDanylo"
status: deprecated
review_date: 2026-11-14
deprecated_on: 2026-11-14
superseded_by: architecture/isd.md
tags: [ops]
---

# Сирі маніфести `k8s/` (ЛР№3 DevOps) — deprecated

!!! warning "Deprecated з 2026-11-14 — актуальне розгортання в Kubernetes: [[isd#isd-k8s|ISD §2.2 (Helm + Argo CD)]]"
    Маніфести `k8s/` не містять canary-Rollout, моніторингу та `existingSecret` і не оновлюються.
    Сторінку не видалено, щоб зберегти історію: її історичний текст — у `k8s/README.md` репозиторію.

Що було: по одному YAML на об'єкт, числові префікси задавали порядок `kubectl apply -f k8s/`
(namespace → конфігурація → Postgres → Redis → RabbitMQ → API → worker). Чому від цього відмовились —
[[adr-0002-gitops-argo-canary-delivery|ADR-0002]].
