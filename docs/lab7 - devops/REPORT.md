# Звіт: Лабораторна робота №7 - Observability і відкат за метриками

Проєкт: Fleet Management (FastAPI), репозиторій `YakymivDanylo/Fleet-management`, кластер minikube (4 CPU, 8 ГБ),
GitOps через Argo CD, стратегія релізу - **canary** (Argo Rollouts, ЛР-6). Namespace застосунку - `fleet`
(у тексті лаби `myapp`), Service - `fleet-management-api`.
Покрокова інструкція демонстрації: [DEMO.md](DEMO.md). Сирі виводи: [evidence/](evidence/).

## 1. Стек моніторингу через Argo CD
Файли `argocd-apps/kps.yaml`, `loki.yaml`, `alloy.yaml` (версії зафіксовано: kube-prometheus-stack 93.0.0,
loki 21.0.0, alloy 1.15.0). `ServerSideApply=true` для kps, селектори `...NilUsesHelmValues: false`,
пароль Grafana у Secret `grafana-admin`, створеному вручну (не в Git). Усі Application-и: `Synced / Healthy`,
поди в `monitoring` - Running (Prometheus, Alertmanager, Grafana, operator, kube-state-metrics, node-exporter, Alloy, Loki).
Помітка: Loki chart 21 відхиляє ключ `minio` зі схеми значень - ключ прибрано (PR #40).

## 2. Метрики застосунку
`src/fleet_management/observability.py`: `GET /metrics`, лічильник `http_requests_total{method,route,status}`
і гістограма `http_request_duration_seconds{route}`. Мітка `route` - шаблон маршруту (`/vehicles/{id}`),
невідомі шляхи зводяться до `unknown` (мала кардинальність); `/metrics`, `/health`, `/livez` не рахуються.
У чарті - `templates/servicemonitor.yaml` (порт `http`). Prometheus -> Targets: 5 цілей
`serviceMonitor/fleet/fleet-management-api` у стані **UP**. Запит
`sum by (status) (rate(http_requests_total{namespace="fleet"}[1m]))` повертає ряди для `200` і `404`.

## 3. Логи
`LOG_FORMAT=json` (рядок = один JSON): `timestamp, level, message, method, route, status, duration_ms, version,
correlation_id`. Рівень `ERROR` для 5xx. Alloy додає мітки `namespace, pod, app`. У Grafana Explore:
`{namespace="fleet"} | json | status >= 500` повертає лише відповіді з кодом 5xx (див. розділ 6).

## 4. Дашборд
`charts/fleet-management/dashboards/fleet-management.json` -> ConfigMap з міткою `grafana_dashboard: "1"`
(`templates/dashboard.yaml`), доставляється Argo CD, підхоплюється sidecar-ом Grafana
("Fleet Management - Observability", uid `fleet-management`). Панелі: запити за секунду, частка 5xx, p95,
5xx по подах, RPS по подах, кількість готових подів, CPU і пам'ять подів, логи помилок і всі логи (Loki).
Перевірка: `GET /api/search?query=Fleet` у Grafana повертає дашборд, якого немає в БД Grafana вручну - він з Git.

## 5. Навантаження
Генератор `docs/lab7/load.yaml` (Deployment `load`, namespace `default`, ~20 запитів/с на репліку; `kubectl scale`
збільшує трафік; для коротких потужних тестів - `hey` з інструкції). Під навантаженням запит до метрики показував
~11 req/s (`200`) + ~3 req/s (`404` на `/nonexistent`), p95 ≈ 4.8 мс. Друга зміна: **видалення пода**
(`kubectl delete pod ...`): под одразу замінено новим, кількість цілей `up` повернулась до 6 за ~25 с
(це видно на панелі "Ready API pods"). Також у розділі 6 показано повний сплеск помилок (частка 5xx ≈ 41 %).

## 6. Автоматичний відкат за метриками
* `templates/analysistemplate.yaml`: AnalysisTemplate `fleet-management-success-rate`, запит частки не-5xx у
  namespace, `successCondition: result[0] >= 0.95`, `interval 30s`, `count 4`, `failureLimit 1`.
* Canary (`values-minikube.yaml`, 5 реплік): `setWeight 20 -> pause 30s -> analysis -> setWeight 60 -> pause 30s`.
  Ручну паузу прибрано.
* "Погана" поведінка: змінна `FAIL_RATE` (`env` у values) - частка запитів з 500 (залежність роутера, health-проби
  не зачіпає).

**Хороший реліз** (образ 1.5.0): AnalysisRun `fleet-management-api-5798f4648d-7-2.1` - **Successful** (4/4),
rollout дійшов до 100 %. Перший запуск без трафіку закінчився `Error` ("no data returned") - це очікувана
поведінка, описана в лабі (0/0 = NaN); після запуску `load` аналіз проходить.

**Поганий реліз** (PR #41, `FAIL_RATE: "0.5"`, evidence: [bad-release.txt](evidence/bad-release.txt)):
`setWeight 20 -> pause -> AnalysisRun Failed`. Виміряні значення успішності: 0.968 (OK), 0.921 (FAIL), 0.913 (FAIL).
Rollout: `Degraded`, "RolloutAborted ... assessed Failed due to failed (2) > failureLimit (1)", Updated: 0,
трафік на stable (ревізія 7, образ 1.5.0, 5 подів).
* Prometheus: `5xx` лише з пода нового ReplicaSet (`...-5f6f6c48fc-s4lgz`, ≈2.6 req/s), решта подів 0
  ([loki-prom-5xx.txt](evidence/loki-prom-5xx.txt)).
* Loki: `{namespace="fleet"} | json | status >= 500` - 214 рядків, усі з єдиного пода `5f6f6c48fc-s4lgz`
  (поле `version=1.5.0` однакове, бо змінився лише env, відрізняє `pod`/pod-template-hash).
* Відкат завершено через Git: `git revert` (PR #42) -> rollout `Healthy`, 5xx зникли.

**Алерт (d)**: `PrometheusRule` `FleetHighErrorRate` (> 5 %, `for: 1m`). Через швидкий abort він не встигає
спрацювати, тому (як радить лаба) поганий реліз випущено без кроку `analysis` (PR "bad release without analysis"):
алерт пройшов **Pending -> Firing** (частка 5xx ≈ 41 %, [alert.txt](evidence/alert.txt)). Потім змінено через
`git revert`.

### Обмеження, виявлене під час демонстрації
Запит аналізу рахує частку успішних запитів по **всьому** namespace. Коли погана версія вже є stable (як у
сценарії алерта), відкат на хорошу версію не проходить аналіз (старі, погані поди ще дають 5xx), і rollout
стає `Degraded`. Вихід: `kubectl argo rollouts promote --full fleet-management-api -n fleet` (після цього
5xx зникли, алерт згас). Точніше рішення - аналізувати лише canary через `rollouts-pod-template-hash`
(необов'язкова частина лаби, не реалізована).

## Керування середовищем
* minikube не перестворювався: ліміт пам'яті наявного контейнера піднято до 8 ГБ (`docker update --memory 8g
  --memory-swap 8g minikube`), 4 CPU.
* Зміни в `main` проходили через PR #39-#43; образи 1.5.0 опубліковано з тегу `v1.5.0` (CI зелений, включно з
  SonarCloud). Тести: 1324 passed, ruff і complexity-гейти проходять.
