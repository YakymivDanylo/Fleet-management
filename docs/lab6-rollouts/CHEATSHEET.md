# Лаб 6 — шпаргалка до захисту (Argo Rollouts, canary)

## 1. Що зроблено (одним абзацом)

API (`fleet-management-api`) розгортається не `Deployment`, а Argo `Rollout` зі стратегією **canary**:
20% → ручна пауза → 60% → 30 с → 80% → 30 с → 100%. Реліз = коміт з новим тегом образу в Git
(GitOps через Argo CD). Контролер Argo Rollouts ставиться окремим Application (sync-wave `-1`),
Helm-чарт має перемикач `rollout.enabled`. Відкат = `abort` (миттєво) + `git revert` (назавжди).

## 2. Чому canary, а не blue-green

- Нова версія отримує лише частку трафіку (тут 1 з 5 подів = 20%), ризик обмежений.
- Не потрібно подвоювати ресурси (blue-green тримає два повні набори; у minikube це зайве).
- Є природні точки для рішення (`pause`): можна promote або abort.
- Мінус (чесно сказати): без ingress/service mesh розподіл йде за кількістю подів, а не за % запитів.

## 3. Архітектура у двох реченнях

`bootstrap/root.yaml` (App-of-Apps) -> `argocd-apps/` -> Application `argo-rollouts` (контролер, wave -1)
і Application `fleet-management` (чарт, має `retry` на випадок гонки CRD).
Спільний pod-template `fleet.apiPodTemplate` використовують і Deployment, і Rollout.

## 4. Порядок демонстрації (команди з реальними значеннями)

Підготовка (вікна): (A) `kubectl argo rollouts get rollout fleet-management-api -n fleet --watch`,
(B) цикл curl у кластері (под `curl`), (C) вільний термінал, (D) Argo CD UI `https://localhost:8080`,
Rollouts dashboard `http://localhost:3100`.

Стартовий стан для показу: API на `1.0.0` (stable), Rollout `Healthy`, 5 подів.

### 4.1. Успішний реліз 1.0.0 -> 1.2.0 (PR #35, коміт `6e9c5b5`)

```powershell
git checkout main; git pull
git checkout -b demo/release-1.2.0
$f = "charts/fleet-management/values-minikube.yaml"
$t = [IO.File]::ReadAllText($f) -replace '(?m)^(  tag: )"1.0.0"','$1"1.2.0"'
[IO.File]::WriteAllText($f, $t)
git diff                       # один рядок: tag: "1.0.0" -> "1.2.0"
git add charts/fleet-management/values-minikube.yaml
git commit -m "chore(infra): release api 1.2.0"
git push -u origin demo/release-1.2.0
gh pr create --base main --fill
gh pr merge demo/release-1.2.0 --squash
git checkout main; git pull
argocd app get fleet-management --refresh
```

Очікуваний результат (так було в прогоні):
- Rollout: `Paused`, `CanaryPauseStep`, крок `1/6`, `SetWeight: 20`, образи `1.0.0 (stable)` і `1.2.0 (canary)`, 1 canary-под + 4 stable.
- curl: переважно `{"version":"1.0.0"}`, приблизно кожна 5-та `{"version":"1.2.0"}`.
- Argo CD: `Synced to main (6e9c5b5)`, `Health Status: Suspended`.

Далі promote:

```powershell
kubectl argo rollouts promote fleet-management-api -n fleet
```

Хід: 60% (3 поди) -> пауза 30 с -> 80% (4 поди) -> пауза 30 с -> 100%.
Фінал: `Healthy`, `1.2.0 (stable)`, 5/5 подів, ревізія 1 `ScaledDown`.

### 4.2. Невдалий реліз 1.3.0 -> 1.4.0, abort і відкат (PR #37, коміт `70b384e`)

```powershell
git checkout main; git pull
git checkout -b demo/release-1.4.0
$f = "charts/fleet-management/values-minikube.yaml"
$t = [IO.File]::ReadAllText($f) -replace '(?m)^(  tag: )"1.3.0"','$1"1.4.0"'
[IO.File]::WriteAllText($f, $t)
git diff                       # один рядок: tag: "1.3.0" -> "1.4.0"
git add charts/fleet-management/values-minikube.yaml
git commit -m "chore(infra): release api 1.4.0"
git push -u origin demo/release-1.4.0
gh pr create --base main --fill
gh pr merge demo/release-1.4.0 --squash
git checkout main; git pull
argocd app get fleet-management --refresh
kubectl argo rollouts get rollout fleet-management-api -n fleet
```

Очікую: `Paused`, крок `1/6`, 20%, `1.3.0 (stable)` + `1.4.0 (canary)`; Argo CD `Synced to main (70b384e)` + `Suspended`.

**Не робити `promote`.** Одразу на паузі:

```powershell
kubectl argo rollouts abort fleet-management-api -n fleet
kubectl argo rollouts get rollout fleet-management-api -n fleet
argocd app get fleet-management
```

Результат (так було): Rollout `Degraded`, `RolloutAborted: Rollout aborted update to revision 4`,
`1.3.0 (stable)`, canary-под `1.4.0` прибрано, 5/5 подів на 1.3.0.
Argo CD: `Synced to main (70b384e)` + `Health Status: Degraded`.

Закріплення через Git:

```powershell
git log --oneline -3                      # 70b384e chore(infra): release api 1.4.0 (#37)
git checkout -b demo/revert-1.4.0
git revert 70b384e --no-edit              # створює bef2449 локально
git push -u origin demo/revert-1.4.0
gh pr create --base main --fill
gh pr merge demo/revert-1.4.0 --squash    # PR #38 -> на main коміт 8f11a75
git checkout main; git pull
argocd app get fleet-management --refresh
kubectl argo rollouts get rollout fleet-management-api -n fleet
```

Результат: спершу Argo CD може показати `OutOfSync from main (8f11a75)` (ще не синхронізувався),
за секунди Rollout стає `Healthy`, `1.3.0 (stable)`, ревізія 5 повторно використала ReplicaSet
`6bd69bc89` (нових подів немає), фінальний Argo CD `Synced to main (8f11a75)` + `Healthy`.

## 5. Що відповісти на «Synced + Degraded»?

- **Sync** = кластер збігається з Git (там ще нова версія, маніфест застосований).
- **Health** = стан робочого навантаження (реліз скасований, працює стара версія).
- Вони вимірюють різне. `abort` лікує поди, але не Git; тому потрібен `git revert`.
  Без revert Argo CD вважатиме Git правдою, а Rollout залишиться `Degraded`.

## 6. Типові питання

- **Чому Rollout не стартує?** Нова ревізія виникає лише при зміні pod-template (тег образу, labels, env).
  Зміна `replicas` чи `strategy` rollout не запускає.
- **Чому змінити `Chart.yaml` небезпечно під час демо?** Лейбла `helm.sh/chart` у pod-template -> перезапуск УСІХ подів.
- **Чому curl-цикл у кластері?** `port-forward` б'є в один под і не показує розподіл.
- **Що таке `pause: {}`?** Пауза без таймера: чекає `promote` вручну. `pause: {duration: 30s}` іде далі сам.
- **Як працює розподіл без ingress?** За співвідношенням кількості подів (5 реплік: 20%=1, 60%=3, 80%=4).
- **Навіщо sync-wave -1 і retry?** Контролер (і CRD `Rollout`) мають існувати до чарту; `retry` з backoff лікує гонку.
- **Нащо `rollout.enabled`?** Можна повернутися на звичайний Deployment без зміни шаблону.
- **Чому образ береться з тегу `v*`?** CI збирає образ з git-тегу; `/version` повертає цей тег (`APP_VERSION`).

## 7. Пастки, які реально траплялись

| Проблема | Причина | Рішення |
|---|---|---|
| Комміт відхилено, PR порожній | `Set-Content` пише CRLF, pre-commit `mixed-line-ending` падає | правити файл через `[IO.File]::ReadAllText/WriteAllText` |
| `gh pr create` каже «no commits» | push пішов з порожньою гілки після відхиленого коміту | перевірити `git log`, закомітити ще раз |
| `abort` нічого не зробив (Healthy) | спершу виконано `promote`, реліз уже 100% | `abort` лише на паузі 20%, без `promote` |
| `--watch` пише «not found» | Rollout ще не створений | повторити після merge |
| `OutOfSync` одразу після revert | Argo CD ще не синхронізувався | зачекати 10-20 с, `argocd app get --refresh` |
| Версії плагіна/контролера різні (1.9.3 / 1.10.1) | мінорний перекіс | сумісно, ігнорувати |
| CI «queued» довго | інцидент GitHub Actions | почекати, не скасовувати |

## 8. Артефакти для скриншотів

1. Rollout `Paused` 20% + curl з мішаними версіями.
2. Argo CD: `Synced` + `Suspended`.
3. Rollout `Healthy` після `promote`.
4. `abort`: Rollout `Degraded` (`RolloutAborted`) + Argo CD `Synced` + `Degraded`.
5. Після `git revert`: Rollout `Healthy`, стара версія stable.
6. Дерево в Argo CD UI та Rollouts dashboard.

## 9. Коміти та PR цього прогону (main)

| Хеш | PR | Що | Що показує |
|---|---|---|---|
| `5c64cf3` | #33 | Контролер Argo Rollouts через Argo CD | етап 2: контролер і CRD |
| `d77924e` | #34 | Canary Rollout в чарті, `rollout.enabled`, `retry`, DEMO.md | етап 3: чарт; Rollout стає Healthy на 1.0.0 |
| `6e9c5b5` | #35 | реліз API 1.2.0 | успішний canary: пауза 20% -> promote -> Healthy |
| `821c56a` | #36 | реліз API 1.3.0 | `abort` виконано після `promote`, 1.3.0 став stable |
| `70b384e` | #37 | реліз API 1.4.0 | показовий `abort` на паузі 20% -> Synced + Degraded |
| `8f11a75` | #38 | `Revert` релізу 1.4.0 | `git revert` -> Healthy на 1.3.0 |

Команда відкату для цього прогону: `git revert 70b384e --no-edit`.
Обидва файли тегу - `charts/fleet-management/values-minikube.yaml` (змінюється один рядок `tag`).

Перевірити хеші наживо: `git log main --oneline -8`.

## 10. Версії для довідки

Argo Rollouts chart `2.43.8` (контролер v1.10.1), плагін `kubectl-argo-rollouts` v1.9.3,
образи `ghcr.io/yakymivdanylo/fleet-management-api:{1.0.0,1.2.0,1.3.0,1.4.0}`, чарт `0.2.0`.
