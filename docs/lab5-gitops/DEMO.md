# ЛР-5 (DevOps): GitOps через Argo CD — сценарій захисту

Усі команди — для **PowerShell**, з каталогу проєкту. Коментарі `#` — що сказати викладачу.

**Вимога завдання (п. 7):** наживо показати пп. 3–6 — інтерфейс Argo CD, реліз комітом, ручну зміну, яку повертає
selfHeal, Synced + Degraded і відкат через `git revert`; а також змінити будь-яке значення в Git і показати, як воно
доїде до кластера.

## Назви в проєкті

| Що | Значення |
|---|---|
| Репозиторій (застосунок + конфігурація, варіант b) | `https://github.com/YakymivDanylo/Fleet-management` (публічний) |
| Чарт / значення для minikube | `charts/fleet-management` / `values-minikube.yaml` (тег образу — тут) |
| Application-и | `root` (App of Apps) і `fleet-management` (namespace Argo CD: `argocd`) |
| Namespace застосунку | `fleet` |
| Deployment / Service API | `fleet-management-api` |
| Secret із паролями (створений вручну, не в Git) | `fleet-secret` |
| Образи | `ghcr.io/yakymivdanylo/fleet-management-{api,worker}:1.0.0` та `:1.1.0` |

## Як кожна зміна потрапляє в Git

Argo CD читає гілку `main`, тож кожна зміна проходить один і той самий цикл: нова гілка → правка → коміт → push →
Pull Request → merge → оновлений `main`. Далі в сценарії він скорочено названий **«цикл змін»**:

```powershell
git checkout -b <назва-гілки>
# ... правка файлу ...
git diff
git commit -am "<повідомлення>"
git push -u origin <назва-гілки>
gh pr create --fill
gh pr merge --merge
git checkout main
git pull
```

Якщо хук `mixed line ending` перервав коміт (він виправляє кінці рядків у файлі), повтори: `git add -A charts argocd-apps`,
потім `git commit -m "<повідомлення>"`.

> Чому PR, а не пряме `git push` у `main`: у проєкті ніхто не працює напряму в `main`.

---

## 1. Перед захистом (за 10 хв)

**Три вікна PowerShell** (усі в каталозі проєкту) і браузер:

| Вікно | Що в ньому працює |
|---|---|
| 1 | `kubectl -n argocd port-forward svc/argocd-server 8080:443` — тунель до інтерфейсу Argo CD |
| 2 | `kubectl -n fleet port-forward svc/fleet-management-api 8081:80` — тунель до застосунку |
| 3 | робоче: усі команди сценарію |
| браузер | `https://localhost:8080` (увійти як `admin`), відкрити `fleet-management` → дерево |

```powershell
minikube start
kubectl -n argocd get pods                  # усі Running
argocd login localhost:8080 --username admin --insecure
argocd app list                             # root і fleet-management: Synced / Healthy
```

### Початковий стан (якщо ти вже проганяв сценарій)

Для показу потрібно: тег `1.0.0` і **вимкнений** selfHeal.

```powershell
git checkout main
git pull
git checkout -b demo/reset
(Get-Content charts/fleet-management/values-minikube.yaml) -replace 'tag: "1.1.0"','tag: "1.0.0"' | Set-Content charts/fleet-management/values-minikube.yaml
```

У редакторі відкрий `argocd-apps/fleet-management.yaml` і **видали рядок** `selfHeal: true` (лишається `prune: true`).

```powershell
git diff                                    # має бути: 2 рядки тегу + прибраний selfHeal
git commit -am "chore(infra): reset demo to 1.0.0 without selfHeal"
git push -u origin demo/reset
gh pr create --fill
gh pr merge --merge
git checkout main
git pull
argocd app get root --refresh
argocd app get fleet-management --refresh
curl.exe localhost:8081/version             # {"version":"1.0.0"}  (якщо тунель обірвався — перезапусти вікно 2)
```

---

## 2. Показ (п. 3–4): Argo CD і дерево об'єктів

```powershell
argocd app list
argocd app get fleet-management
helm list -n fleet
```

- `argocd app list` — два застосунки. **root** — «застосунок над застосунками» (App of Apps): я вручну застосовував
  лише `bootstrap/root.yaml`, а `fleet-management` Argo CD створив сам з Git (каталог `argocd-apps/`).
- **Synced** — кластер збігається з Git. **Healthy** — усе розгорнуте працює. Це два незалежні статуси.
- `helm list` порожній: Argo CD використовує Helm лише як шаблонізатор (рендерить YAML), реліз Helm не створює.
- Секрети в Git не зберігаються: паролі лежать у `fleet-secret`, створеному вручну; чарт читає його через
  `existingSecret: fleet-secret`.

**У браузері:** `root` → `fleet-management` → дерево: Deployment → ReplicaSet → Pod, Service, ConfigMap, PVC.

```powershell
curl.exe localhost:8081/version             # {"version":"1.0.0"}
```

---

## 3. Реліз комітом (п. 5)

```powershell
git checkout -b release/1.1.0
(Get-Content charts/fleet-management/values-minikube.yaml) -replace 'tag: "1.0.0"','tag: "1.1.0"' | Set-Content charts/fleet-management/values-minikube.yaml
git diff                                    # змінився лише тег образу (api і worker)
git commit -am "chore(infra): release fleet-management 1.1.0"
git push -u origin release/1.1.0
gh pr create --fill
gh pr merge --merge
git checkout main
git pull

argocd app get fleet-management --refresh   # не чекати періодичного опитування Git (до 3 хв)
kubectl -n fleet get pods -w                # Ctrl+C коли нові поди Running
```

- **Руками в кластері я нічого не змінював** — лише тег у Git. Argo CD побачив новий коміт, порівняв його з
  кластером (**OutOfSync**), сам синхронізував і запустив rolling update.
- **Rolling update** — Kubernetes піднімає нові поди по одному, а старі прибирає лише коли нові готові
  (`maxUnavailable: 0`): простою немає.
- `--refresh` = кнопка **Refresh** в інтерфейсі: «перечитай Git зараз».

Після заміни подів перезапусти тунель у вікні 2 (він був прив'язаний до старого пода), потім:

```powershell
curl.exe localhost:8081/version             # {"version":"1.1.0"}
argocd app history fleet-management         # кожна синхронізація прив'язана до коміту
```

---

## 4. Дрейф і selfHeal (п. 6а)

**Дрейф** — розбіжність між Git і кластером після ручної зміни. **selfHeal** — режим, у якому Argo CD сам виправляє
дрейф, повертаючи значення з Git.

Без selfHeal:

```powershell
kubectl -n fleet scale deployment fleet-management-api --replicas=5
argocd app get fleet-management --refresh   # Sync Status: OutOfSync
kubectl -n fleet get deploy fleet-management-api   # 5/5 — Argo CD бачить дрейф, але не виправляє
```

- У браузері: жовтий **OutOfSync**, кнопка **Diff** показує `replicas: 2` проти `5`.

Вмикаємо selfHeal — теж через Git (`root` сам застосує зміну опису Application):

```powershell
git checkout -b feat/enable-selfheal
```

У редакторі відкрий `argocd-apps/fleet-management.yaml` і заміни рядок `prune: true ...` на два рядки:

```yaml
      prune: true
      selfHeal: true
```

```powershell
git diff                                    # додався рядок selfHeal: true
git commit -am "chore(infra): enable selfHeal for fleet-management"
git push -u origin feat/enable-selfheal
gh pr create --fill
gh pr merge --merge
git checkout main
git pull
argocd app get root --refresh
argocd app get fleet-management --refresh
```

Повторюємо ручну зміну:

```powershell
kubectl -n fleet scale deployment fleet-management-api --replicas=5
kubectl -n fleet get deploy fleet-management-api -w     # за секунди знову 2/2 — Ctrl+C
```

- З `selfHeal: true` Argo CD сам повертає значення з Git. **Правда — у Git, а не в кластері.**

---

## 5. Synced, але Degraded (п. 6б)

```powershell
git checkout -b test/bad-tag
(Get-Content charts/fleet-management/values-minikube.yaml) -replace 'tag: "1.1.0"','tag: "9.9.9"' | Set-Content charts/fleet-management/values-minikube.yaml
git diff
git commit -am "chore(infra): deploy non-existent image tag 9.9.9"
git push -u origin test/bad-tag
gh pr create --fill
gh pr merge --merge
git checkout main
git pull

argocd app get fleet-management --refresh   # Synced; Health: Progressing → через ~2 хв Degraded
kubectl -n fleet get pods                   # нові поди: ErrImagePull / ImagePullBackOff, старі Running
curl.exe localhost:8081/version             # досі 1.1.0 — застосунок працює
```

- **Sync ≠ Health.** Sync: «кластер збігається з Git?» — так, маніфест застосовано. Health: «працює?» — ні, образу
  `9.9.9` не існує (`ImagePullBackOff` — под не може завантажити образ і повторює спроби з наростаючою паузою).
- `Degraded` з'являється не одразу: Kubernetes чекає `progressDeadlineSeconds: 120` і лише потім вважає розгортання
  проваленим.
- Старі поди не вимкнено (`maxUnavailable: 0`) — користувачі не постраждали.
- У браузері: в шапці **Degraded** + **Synced**, у дереві червоні нові поди.

---

## 6. Відкат через `git revert` (п. 6в)

```powershell
git log --oneline -5                        # знайти хеш коміту "deploy non-existent image tag 9.9.9"
git checkout -b revert/bad-tag
git revert --no-edit <ХЕШ_КОМІТУ_З_9.9.9>   # НЕ merge-коміт, а сам коміт зі зміною тегу
git push -u origin revert/bad-tag
gh pr create --fill
gh pr merge --merge
git checkout main
git pull

argocd app get fleet-management --refresh   # Synced / Healthy (за 10–20 с)
kubectl -n fleet get pods                   # зіпсованих подів більше немає
argocd app history fleet-management         # нова ревізія після відкату
git log --oneline -6
curl.exe localhost:8081/version             # {"version":"1.1.0"}
```

- **`git revert`** створює **новий коміт**, що скасовує зміну. Історія не переписується: поганий коміт лишається в
  `git log`, видно хто, що і коли змінив. Це відкат **опису**, а не кластера.
- Чому не `argocd app rollback`: він працює лише з вимкненою автосинхронізацією, інакше Argo CD одразу поверне стан
  із Git. До того ж кластер і Git розійшлись би.
- Відкат миттєвий: Kubernetes повторно використав старий ReplicaSet, нові поди не створюються.

---

## 7. Якщо викладач просить змінити інше значення

Будь-яка зміна — лише через Git, у `charts/fleet-management/values-minikube.yaml`. Приклад: 3 репліки API.

```powershell
git checkout -b demo/replicas
(Get-Content charts/fleet-management/values-minikube.yaml) -replace '(?m)^replicaCount: \d+','replicaCount: 3' | Set-Content charts/fleet-management/values-minikube.yaml
git diff
git commit -am "chore(infra): scale api to 3 replicas"
git push -u origin demo/replicas
gh pr create --fill
gh pr merge --merge
git checkout main
git pull
argocd app get fleet-management --refresh
kubectl -n fleet get pods
```

Інший приклад — назва застосунку (змінює ConfigMap, поди перезапустяться), перевірка через `/info`:

```powershell
git checkout -b demo/appname
(Get-Content charts/fleet-management/values-minikube.yaml) -replace 'appName: ".*"','appName: "Fleet Management (DEMO)"' | Set-Content charts/fleet-management/values-minikube.yaml
git diff
git commit -am "chore(infra): change app name"
git push -u origin demo/appname
gh pr create --fill
gh pr merge --merge
git checkout main
git pull
argocd app get fleet-management --refresh
curl.exe localhost:8081/info
```

- Принцип: не «зміню руками в кластері», а «змінюю в Git, Argo CD доставляє». Інші значення: змінні середовища —
  `config.*`, ліміти — `resources.*` у `values-minikube.yaml`.

---

## 8. Короткі відповіді на можливі питання

| Питання | Відповідь |
|---|---|
| Що таке GitOps? | Бажаний стан кластера описаний у Git; агент у кластері (Argo CD) сам приводить кластер до нього. |
| Навіщо `root`? | Application теж треба кимось створити. `root` — єдиний вручну застосований; решта береться з `argocd-apps/` у Git. |
| Що робить `prune`? | Об'єкт, видалений з Git, Argo CD видаляє й з кластера. |
| Що робить `selfHeal`? | Повертає значення з Git після ручних змін у кластері. |
| Де паролі? | Не в Git. `fleet-secret` створено вручну; чарт читає його через `existingSecret`. Для production — Sealed Secrets / SOPS / External Secrets. |
| Чому образи з тегом, а не `latest`? | Тег фіксує версію: за Git видно, що саме розгорнуто, і можна відкотитись. `latest` не відтворюється. |
| Чому `helm list` порожній? | Argo CD лише рендерить шаблони (`helm template`), сам Helm-реліз не створюється. |
| Чому відкат комітом? | Відкочується опис, історія зберігається; `argocd app rollback` із автосинхронізацією не працює. |

---

## 9. Відновлення «з нуля» (якщо кластер втрачено)

```powershell
minikube start
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd get pods -w                                   # чекати Running (Ctrl+C)
kubectl -n argocd port-forward svc/argocd-server 8080:443       # у вікні 1
argocd admin initial-password -n argocd                         # початковий пароль admin
argocd login localhost:8080 --username admin --insecure
argocd account update-password
kubectl -n argocd delete secret argocd-initial-admin-secret

function New-Hex($n) { $b = New-Object byte[] $n; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); -join ($b | ForEach-Object { $_.ToString('x2') }) }
kubectl create namespace fleet
kubectl -n fleet create secret generic fleet-secret --from-literal=POSTGRES_PASSWORD=$(New-Hex 16) --from-literal=RABBITMQ_DEFAULT_USER=fleet --from-literal=RABBITMQ_DEFAULT_PASS=$(New-Hex 16) --from-literal=JWT_SECRET_KEY=$(New-Hex 32)
kubectl apply -f bootstrap/root.yaml                            # єдиний ручний apply
```

(`New-Hex` — одноразова функція лише для генерації випадкових паролів Secret, у сценарії захисту не використовується.)

## Типові проблеми

| Симптом | Причина / дія |
|---|---|
| `curl` повертає `Temporary Redirect` | на 8081 слухає не застосунок — перезапусти тунель у вікні 2 (`svc/fleet-management-api 8081:80`) |
| `/version` зі старою версією після релізу | тунель прив'язаний до старого пода — перезапусти вікно 2 |
| Хук `mixed line ending` перервав коміт | `git add -A charts argocd-apps` і `git commit -m "..."` ще раз |
| `git checkout main` каже про локальні зміни | лише різниця кінців рядків: `git checkout -- charts argocd-apps` |
| `OutOfSync` одразу після `--refresh` | Argo CD ще синхронізує — повтори команду через 10–20 с |
| `ImagePullBackOff` на `1.0.0`/`1.1.0` | пакет GHCR приватний або тег не опубліковано |
| Поди `CreateContainerConfigError` | немає `fleet-secret` у namespace `fleet` |

## Прибирання (після захисту)

```powershell
argocd app delete root --cascade            # видаляє root, fleet-management і всі їхні об'єкти
kubectl delete namespace fleet argocd
minikube stop
```
