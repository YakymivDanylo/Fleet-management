# ЛР-6 (DevOps): Progressive delivery з Argo Rollouts — сценарій захисту

Команди — для **PowerShell**, з каталогу проєкту. Коментарі `#` — що сказати викладачу.

## Що зроблено

| Вимога | Де в репозиторії |
|---|---|
| Контролер Argo Rollouts з Git | `argocd-apps/argo-rollouts.yaml` (чарт `argo/argo-rollouts` 2.43.8, sync-wave `-1`) |
| `retry` для застосунку (CRD ще не готові) | `argocd-apps/fleet-management.yaml` |
| Rollout замість Deployment за прапорцем | `charts/fleet-management/templates/api-rollout.yaml`, `api-deployment.yaml` (`if not rollout.enabled`) |
| Один шаблон пода для обох | `charts/fleet-management/templates/_api-pod.tpl` (хелпер `fleet.apiPodTemplate`) |
| Стратегія canary, 5 реплік | `values-minikube.yaml` → `rollout.strategy` |
| Версія чарту | `Chart.yaml`: 0.1.0 → 0.2.0 |

Rollout керує лише **API** (`fleet-management-api`, namespace `fleet`); worker, Postgres, Redis, RabbitMQ — звичайні Deployment-и.

## Чому canary

API stateless, а `/version` дозволяє побачити співвідношення версій. Canary дає ручну паузу на 20 % трафіку
(1 з 5 подів) для перевірки на реальному трафіку, не вимагає подвоєння ресурсів (blue-green одразу піднімає
повну копію — 5 додаткових подів на minikube) і дозволяє відкат на ранньому кроці з мінімальним ураженням користувачів.
Мінус: деякий час співіснують дві версії API, тому зміни схеми БД мають бути зворотно сумісними.

Кроки: `setWeight 20` → `pause {}` (ручний promote) → `setWeight 60` → `pause 30s` → `setWeight 80` → `pause 30s` → 100 %.
Без traffic router співвідношення задається кількістю подів: 20 % = 1/5, 60 % = 3/5, 80 % = 4/5.

## 1. Підготовка

Образи (потрібні щонайменше три версії API): `git tag v1.2.0 && git push origin v1.2.0` (CI збере
`ghcr.io/yakymivdanylo/fleet-management-api:1.2.0`), так само `v1.3.0` (для abort) і запасна `v1.4.0`.
Поточна — `1.0.0`.

```powershell
minikube start
kubectl -n argocd port-forward svc/argocd-server 8080:443        # вікно 1
kubectl -n fleet port-forward svc/fleet-management-api 8081:80    # вікно 2
argocd login localhost:8080 --username admin --insecure
```

Плагін (один раз): завантажити `kubectl-argo-rollouts-windows-amd64` зі сторінки релізів
https://github.com/argoproj/argo-rollouts/releases, перейменувати в `kubectl-argo-rollouts.exe`, покласти в каталог з PATH.

```powershell
kubectl argo rollouts version
```

## 2. Контролер окремим комітом (порядок важливий)

Спочатку злити в `main` лише `argocd-apps/argo-rollouts.yaml`, дочекатися Healthy, і тільки потім — зміни чарту.

```powershell
argocd app get root --refresh
argocd app get argo-rollouts                 # Synced / Healthy
kubectl -n argo-rollouts get pods
kubectl get crd | Select-String argoproj     # rollouts.argoproj.io, analysistemplates...
```

Далі зливаємо чарт (Rollout + `retry`). Helm/Argo CD видалить Deployment і створить Rollout — короткий простій
тут нормальний. У дереві Argo CD з'являється Rollout → ReplicaSet-и → поди.

```powershell
kubectl argo rollouts get rollout fleet-management-api -n fleet
```

## 3. Реліз комітом (п. 4)

Окремі термінали:

```powershell
kubectl argo rollouts get rollout fleet-management-api -n fleet --watch      # вікно 3
kubectl argo rollouts dashboard                                              # http://localhost:3100
# цикл запитів ВСЕРЕДИНІ кластера (port-forward б'є в один под і розподілу не покаже)
kubectl -n fleet run curl --rm -it --image=curlimages/curl -- sh -c 'while true; do curl -s http://fleet-management-api/version; echo; sleep 0.5; done'
```

```powershell
git checkout -b demo/release-1.2.0
(Get-Content charts/fleet-management/values-minikube.yaml) -replace '(?m)^(  tag: )"1.0.0"','$1"1.2.0"' | Set-Content charts/fleet-management/values-minikube.yaml
git diff                                     # лише тег API (worker має свій тег глибше)
git commit -am "chore(infra): release api 1.2.0"
git push -u origin demo/release-1.2.0
gh pr create --fill; gh pr merge --merge
git checkout main; git pull
argocd app get fleet-management --refresh
argocd app get fleet-management              # Health Status: Suspended
```

# Rollout стоїть на `pause: {}`: 1 новий под з 5, у циклі приблизно кожна п'ята відповідь — `1.2.0`.
# Health = Suspended — це пауза Rollout, а не помилка.

```powershell
kubectl argo rollouts promote fleet-management-api -n fleet     # або в UI Argo CD: Rollout → ⋮ → Promote-Full / Resume
```

# 60 % → пауза 30 с → 80 % → пауза 30 с → 100 %. Статус Healthy, стабільна ревізія 1.2.0.

## 4. Скасування (п. 5)

Змінити тег на `1.3.0`, push/merge, дочекатися першої паузи (20 %):

```powershell
kubectl argo rollouts abort fleet-management-api -n fleet
kubectl argo rollouts get rollout fleet-management-api -n fleet   # Status: Degraded, stable — 1.2.0
argocd app get fleet-management                                    # Sync: Synced, Health: Degraded
```

# Synced — маніфест у кластері збігається з Git (там тег 1.3.0). Degraded — реліз скасовано й працює стара версія,
# тобто фактичний стан не відповідає бажаному. Це два незалежні виміри: Sync порівнює з Git, Health — стан ресурсів.
# Завершуємо через Git:

```powershell
git revert <коміт із 1.3.0> --no-edit
git push                                                           # або через PR
argocd app get fleet-management --refresh
kubectl argo rollouts get rollout fleet-management-api -n fleet    # Healthy, 1.2.0
```

Альтернатива, якщо проблему виправлено поза образом: `kubectl argo rollouts retry rollout fleet-management-api -n fleet`.

## Типові проблеми

- `no matches for kind "Rollout"` / SyncFailed — застосунок синхронізувався до появи CRD; є `retry`, або Sync вручну після Healthy в `argo-rollouts`.
- Реліз не стартує — Rollout реагує лише на зміну шаблону пода (образ, змінні, мітки), не на `replicas` чи стратегію.
  Зверніть увагу: мітка пода `helm.sh/chart` містить версію чарту, тому її зміна теж запускає реліз.
- Canary «не ділить» — запити робити зсередини кластера, не через port-forward.
