# Звіт з лабораторної роботи 6. Progressive delivery з Argo Rollouts (canary)

Проєкт: Fleet Management (FastAPI, Postgres, RabbitMQ, Redis), кластер minikube, GitOps через Argo CD.

## 1. Мета

Замінити звичайний `Deployment` API на `Rollout` з поступовим (canary) розгортанням, керованим з Git,
і показати два сценарії: успішний реліз із ручним підтвердженням та скасований реліз із відкатом.

## 2. Обрана стратегія і обґрунтування

Canary. Нова версія спершу отримує малу частку трафіку, ризик обмежений, а на паузах можна ухвалити рішення
(`promote` або `abort`). Blue-green вимагав би тримати два повні набори подів, що зайве для minikube.
Обмеження: без ingress або service mesh розподіл іде за кількістю подів, а не за відсотком запитів
(5 реплік: 20% = 1 под, 60% = 3, 80% = 4).

Кроки стратегії (`values-minikube.yaml`):

| Крок | Дія |
|---|---|
| 1 | `setWeight: 20` |
| 2 | `pause: {}` (чекає `promote` вручну) |
| 3 | `setWeight: 60` |
| 4 | `pause: {duration: 30s}` |
| 5 | `setWeight: 80` |
| 6 | `pause: {duration: 30s}`, далі 100% |

## 3. Що реалізовано

| Зміна | Файл | PR / коміт |
|---|---|---|
| Контролер Argo Rollouts як Application, sync-wave `-1`, chart `2.43.8` | `argocd-apps/argo-rollouts.yaml` | #33, `5c64cf3` |
| `retry` з backoff для Application з чартом (гонка CRD) | `argocd-apps/fleet-management.yaml` | #34, `d77924e` |
| Спільний pod-template для Deployment і Rollout | `charts/fleet-management/templates/_api-pod.tpl` | #34, `d77924e` |
| Ресурс `Rollout` під перемикачем `rollout.enabled` | `charts/fleet-management/templates/api-rollout.yaml` | #34, `d77924e` |
| Deployment вимикається, коли `rollout.enabled` | `charts/fleet-management/templates/api-deployment.yaml` | #34, `d77924e` |
| Значення за замовчуванням і JSON-схема для `rollout` | `values.yaml`, `values.schema.json` | #34, `d77924e` |
| Canary-кроки, 5 реплік | `values-minikube.yaml` | #34, `d77924e` |
| Версія чарту 0.1.0 -> 0.2.0 | `Chart.yaml` | #34, `d77924e` |
| Інструкція демонстрації | `docs/lab6-rollouts/DEMO.md` | #34, `d77924e` |

Перевірка шаблону: `helm template` для режиму без Rollout дав маніфест, ідентичний до змін (для default і minikube значень),
`helm lint` пройшов.

## 4. Хід виконання

Реліз виконується комітом у Git (зміна тегу образу API в `values-minikube.yaml`), далі PR зі squash-merge.
Образи збираються CI з git-тегів `v*`; доступні `1.0.0`, `1.2.0`, `1.3.0`, `1.4.0` у `ghcr.io/yakymivdanylo/fleet-management-api`.

### 4.1. Контролер (PR #33, `5c64cf3`)

Після merge Argo CD (root App-of-Apps) встановив контролер у namespace `argo-rollouts`, з'явилися CRD `Rollout`.
Плагін `kubectl argo rollouts` v1.9.3, контролер v1.10.1 (мінорна різниця версій, сумісні).

[скриншот: `argocd app get root` і `argo-rollouts`, поди `argo-rollouts`, `kubectl get crd | findstr rollout`]

### 4.2. Чарт з Rollout (PR #34, `d77924e`)

Rollout `fleet-management-api` створено, 5 подів на `1.0.0`, статус `Healthy`.
Deployment для API замінено Rollout, решта сервісів (postgres, rabbitmq, redis, worker) без змін.

[скриншот: `--watch` з `Healthy`, `argocd app get fleet-management`, `kubectl get pods,deploy -n fleet`]

### 4.3. Успішний canary-реліз 1.0.0 -> 1.2.0 (PR #35, `6e9c5b5`)

Після merge Rollout зупинився на першій паузі:

```
Status:          Paused
Message:         CanaryPauseStep
Step:            1/6
SetWeight:       20
ActualWeight:    20
Images:          ...fleet-management-api:1.0.0 (stable)
                 ...fleet-management-api:1.2.0 (canary)
revision:2  canary  1 pod
revision:1  stable  4 pods
```

Argo CD: `Synced to main (6e9c5b5)`, `Health Status: Suspended`. Цикл запитів у кластері показував суміш
`{"version":"1.0.0"}` і `{"version":"1.2.0"}` приблизно у співвідношенні 4:1.

Після `kubectl argo rollouts promote fleet-management-api -n fleet`:

```
rollout 'fleet-management-api' promoted
Step 3/6  SetWeight: 60  ActualWeight: 60   (3 нові поди, пауза 30 с)
Step 4/6  SetWeight: 80  ActualWeight: 75 -> 80
Step 5/6  Paused 80%                          (пауза 30 с)
Step 6/6  SetWeight: 100
Status: Healthy
Images: ...fleet-management-api:1.2.0 (stable)
Replicas: Desired 5, Current 5, Updated 5, Ready 5, Available 5
revision:1  ReplicaSet  ScaledDown
```

[скриншоти: Paused 20% + curl з мішаними версіями; Argo CD Synced/Suspended; Healthy після promote]

### 4.4. Перша спроба скасування (1.2.0 -> 1.3.0, PR #36, `821c56a`)

Нюанс виконання: `abort` було подано вже після `promote`, коли реліз дійшов до 100%.

```
> kubectl argo rollouts promote fleet-management-api -n fleet
rollout 'fleet-management-api' promoted
> kubectl argo rollouts abort fleet-management-api -n fleet
rollout 'fleet-management-api' aborted
Status: Healthy   Images: ...:1.3.0 (stable)   revision:3 stable 5 pods
Argo CD: Synced to main (821c56a), Health Status: Healthy
```

`abort` нічого не змінив: на 100% нема що скасовувати, `1.3.0` став новою стабільною версією.
Висновок: `abort` діє тільки під час незавершеного canary (на паузі).
Сценарій скасування повторено на `1.4.0`.

### 4.5. Скасований реліз 1.3.0 -> 1.4.0 і відкат (PR #37, `70b384e`; PR #38, `8f11a75`)

Реліз 1.4.0 зупинився на паузі 20%:

```
Status:          Paused
Step:            1/6   SetWeight: 20   ActualWeight: 20
Images:          ...:1.3.0 (stable)
                 ...:1.4.0 (canary)
Replicas:        Desired 5, Current 5, Updated 1, Ready 5, Available 5
revision:4  canary  fleet-management-api-84c595767d  1 pod
revision:3  stable  fleet-management-api-6bd69bc89   4 pods
Argo CD: Synced to main (70b384e), Health Status: Suspended
```

Скасування без `promote`:

```
> kubectl argo rollouts abort fleet-management-api -n fleet
rollout 'fleet-management-api' aborted

Status:          Degraded
Message:         RolloutAborted: Rollout aborted update to revision 4
Step:            0/6   SetWeight: 0   ActualWeight: 0
Images:          ...:1.3.0 (stable)
Replicas:        Desired 5, Current 5, Updated 0, Ready 5, Available 5
revision:4  ReplicaSet  ScaledDown
revision:3  ReplicaSet  Healthy (stable), 5 pods

Argo CD: Synced to main (70b384e), Health Status: Degraded
```

Canary-под `1.4.0` завершено, до stable-набору автоматично додано п'ятий под.

Чому `Synced` разом з `Degraded`: Sync показує, що кластер збігається з Git (там тег 1.4.0), Health показує,
що реліз скасовано й працює стара версія. `abort` виправляє кластер, але не Git, тому відкат закріплюється комітом.

Відкат через Git:

```
> git revert 70b384e --no-edit
[demo/revert-1.4.0 bef2449] Revert "chore(infra): release api 1.4.0 (#37)"
> gh pr merge demo/revert-1.4.0 --squash
Squashed and merged pull request #38 (Revert "chore(infra): release api 1.4.0 (#37)")
> git pull     (70b384e..8f11a75)

Argo CD (одразу): OutOfSync from main (8f11a75), Rollout OutOfSync / Degraded
Rollout (за секунди):
Status:          Healthy
Step:            6/6   SetWeight: 100   ActualWeight: 100
Images:          ...:1.3.0 (stable)
revision:5  fleet-management-api-6bd69bc89  Healthy, 5 pods (той самий ReplicaSet)
revision:4  ScaledDown
```

Після `revert` pod-template збігся зі стабільною ревізією, тому контролер повторно використав ReplicaSet `6bd69bc89`
і нових подів не створював. Стан Git і кластера знову узгоджений.

[скриншоти: Paused 20% (1.4.0 canary); abort -> Degraded; Argo CD Synced + Degraded; PR #38; Healthy після revert; Argo CD UI дерево]

## 5. Підсумкова таблиця подій

| # | Версія | PR | Коміт на main | Дія | Результат |
|---|---|---|---|---|---|
| 1 | контролер | #33 | `5c64cf3` | merge | Argo Rollouts встановлено |
| 2 | чарт | #34 | `d77924e` | merge | Rollout Healthy на 1.0.0 |
| 3 | 1.2.0 | #35 | `6e9c5b5` | release + promote | canary 20/60/80/100, Healthy |
| 4 | 1.3.0 | #36 | `821c56a` | release + promote + abort | abort на 100% безпредметний, 1.3.0 stable |
| 5 | 1.4.0 | #37 | `70b384e` | release + abort на 20% | Degraded, Synced |
| 6 | revert 1.4.0 | #38 | `8f11a75` | git revert | Healthy на 1.3.0, нових подів нема |

## 6. Проблеми й рішення

| Проблема | Причина | Рішення |
|---|---|---|
| Коміт релізу 1.2.0 відхилив pre-commit, PR вийшов порожнім | `Set-Content` у PowerShell пише CRLF, хук `mixed-line-ending` | змінювати тег через `[IO.File]::ReadAllText/WriteAllText`, повторити коміт |
| `abort` після `promote` не дав ефекту | реліз уже дійшов до 100% | подавати `abort` лише на паузі, повторено на 1.4.0 |
| CI довго `queued` | інцидент GitHub Actions | дочекатися, образи зібрано |
| `--watch` писав «not found» до merge | Rollout ще не існував | повторити після merge |

## 7. Висновки

1. Rollout з canary дає керований реліз: відсоток нової версії зростає кроками, на паузі є час перевірити стан.
2. `promote` продовжує реліз, `abort` повертає всі поди на стабільну версію за секунди, не чекаючи змін у Git.
3. Argo CD показує Sync і Health незалежно: `Synced + Degraded` означає «Git має нову версію, у кластері працює стара».
4. Остаточний відкат робиться `git revert` у Git, після чого Rollout повертається в `Healthy` без нових подів.
5. Реліз = коміт у Git, відкат = revert-коміт, тому історія змін прозора й відтворювана.

## 8. Додатки

- Інструкція демонстрації: `docs/lab6-rollouts/DEMO.md`
- Шпаргалка до захисту: `docs/lab6-rollouts/CHEATSHEET.md`
