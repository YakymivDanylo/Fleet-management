---
title: ADR-0002
owner: "@YakymivDanylo"
status: published
adr_status: Accepted
decision_date: 2026-10-26
review_date: 2027-05-13
review_cycle_days: 180
tags: [architecture, adr]
---

# ADR-0002: GitOps-доставка через Argo CD і canary-релізи Argo Rollouts з автоматичним відкатом за метриками

- **Статус:** Accepted (замінює неформальне рішення «`kubectl apply -f k8s/` вручну», ЛР№3 DevOps)
- **Дата рішення:** 2026-10-26 (Argo CD, ЛР№5), 2026-11-04 (canary Rollout, ЛР№6), 2026-11-07 (analysis-відкат, ЛР№7)
- **Дата запису:** 2026-11-14
- **Автор / власник:** Danylo Yakymiv
- **Пов'язані документи:** [ISD §2.2, §2.3, §6](../isd.md#isd-k8s), `argocd-apps/`, `charts/fleet-management/`

## Контекст

Перші розгортання в minikube виконувались вручну (`kubectl apply -f k8s/`, потім `helm upgrade`). Стан
кластера розходився з Git (ручні правки), відкат вимагав пам'ятати попередню ревізію, а поганий реліз
(демо `FAIL_RATE=0.5`) відразу отримував 100 % трафіку.

Потрібно: (1) кластер = Git; (2) реліз і відкат — через PR, з аудитом; (3) поганий реліз має зачепити
меншу частку користувачів і відкотитися **без людини**.

## Розглянуті альтернативи

| # | Варіант | Плюси | Мінуси |
|---|---|---|---|
| A | `kubectl apply` / `helm upgrade` з ноутбука | просто, без додаткових контролерів | дрейф кластера від Git, немає аудиту, ручний відкат |
| B | CI push-деплой (GitHub Actions → `helm upgrade` у кластер) | автоматизація | CI потребує kubeconfig з правами на кластер; minikube недоступний з GitHub runner; дрейф не лікується |
| C | **Argo CD (pull, selfHeal) + Argo Rollouts canary + AnalysisTemplate на Prometheus** (обрано) | Git — єдине джерело; selfHeal скасовує ручні правки; canary 20 % → аналіз → 60 % → 100 %; автоматичний abort при < 95 % успішних відповідей | два додаткові контролери (Argo CD, Rollouts) і стек моніторингу; CRD `Rollout` має існувати до синку застосунку (retry у Application) |
| D | Argo CD + Blue-Green | миттєве перемикання, простий відкат | подвоєння ресурсів на час релізу; немає поступового впливу на частку користувачів |

## Рішення

- `bootstrap/root.yaml` (app-of-apps) керує `argocd-apps/`: `fleet-management`, `argo-rollouts`,
  `kube-prometheus-stack`, `loki`, `alloy` — версії чартів зафіксовані.
- Застосунок `fleet-management` — `automated: {prune: true, selfHeal: true}`, retry 5×.
- API розгортається як `Rollout` (5 реплік) з кроками `setWeight 20 → pause 30s → analysis → setWeight 60 →
  pause 30s → 100 %`; `AnalysisTemplate fleet-management-success-rate` — частка не-5xx ≥ 95 %, 4 виміри
  через 30 с, `failureLimit: 1`.
- Реліз = тег `vX.Y.Z` (CI публікує образ у GHCR) + PR зі зміною `image.tag` у `values-minikube.yaml`.
- Каталог `k8s/` позначено **deprecated** — він не відображає canary, моніторинг і `existingSecret`.

## Наслідки

- ✅ Поганий реліз отримує ≤ 20 % трафіку ~2 хв і відкочується автоматично; MTTR не залежить від людини.
- ✅ Кожна зміна кластера — коміт; відкат = `git revert`.
- ⚠️ Secret `fleet-secret` створюється поза Git (ручний крок у handover-інструкції; кандидат — Sealed Secrets).
- ⚠️ Аналіз залежить від Prometheus: якщо метрик немає, AnalysisRun може завершитися `Error`/`Inconclusive` —
  моніторинг сам стає критичною залежністю релізу.
- ⚠️ Для нового інженера вища поріг входу (Argo CD, Rollouts, Helm) — компенсується ISD §2.2 і [[handover]].
