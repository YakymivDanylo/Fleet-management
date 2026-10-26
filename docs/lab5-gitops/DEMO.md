# ЛР-5 (DevOps): GitOps через Argo CD — сценарій для захисту

Усі команди — для **Git Bash** (на Windows). Назви в цьому проєкті:

| Що | Значення |
|---|---|
| Репозиторій (і застосунок, і конфігурація — варіант b) | `https://github.com/YakymivDanylo/Fleet-management.git` (публічний) |
| Чарт | `charts/fleet-management`, значення для minikube — `values-minikube.yaml` |
| Application (він же Helm-реліз) | `fleet-management` (namespace Argo CD: `argocd`) |
| Namespace застосунку | `fleet` |
| Service / Deployment API | `fleet-management-api` |
| Secret із паролями (створюється вручну) | `fleet-secret` |
| Образи | `ghcr.io/yakymivdanylo/fleet-management-api` та `...-worker`, теги `1.0.0`, `1.1.0` |

Шпаргалка «що де лежить у Git»:

```
bootstrap/root.yaml                            # кореневий Application — єдине, що застосовується руками
argocd-apps/fleet-management.yaml              # Application нашого чарту (його підхоплює root)
charts/fleet-management/                       # чарт із ЛР-4 (+ existingSecret, progressDeadlineSeconds)
charts/fleet-management/values-minikube.yaml   # тег образу — ТЕ, що змінюємо при релізі
```

---

## Частина A. Підготовка (робиться ОДИН раз, до захисту)

### A1. Злити гілку в `main` і опублікувати образи двох версій

Argo CD читає `targetRevision: main`, тож `bootstrap/`, `argocd-apps/`, `charts/` мають бути в `main`.

```bash
# після merge PR feat/lab5-gitops -> main
git checkout main && git pull
git tag v1.0.0 && git push origin v1.0.0     # CI збирає і публікує ghcr.io/.../fleet-management-{api,worker}:1.0.0
git tag v1.1.0 && git push origin v1.1.0     # те саме для 1.1.0 (готуємо наперед для п. 5)
```

**Пояснення.** Пуш тегу `vX.Y.Z` запускає `.github/workflows/ci.yml`; job `publish` збирає образи з
`--build-arg APP_VERSION=X.Y.Z` і пушить їх у GHCR з тегом `X.Y.Z` (не `latest`). Версія «вшита» в образ,
тому `GET /version` повертає `{"version": "1.1.0"}`. Пуш змін у `bootstrap/`, `argocd-apps/`, `charts/`, `docs/`
образ **не** перезбирає (`paths-ignore`).

### A2. Зробити пакети публічними

GitHub → профіль → *Packages* → `fleet-management-api` → *Package settings* → *Change visibility* → **Public**.
Те саме для `fleet-management-worker`. Інакше під у кластері отримає `ImagePullBackOff`.

Перевірка без автентифікації:

```bash
docker logout ghcr.io
docker pull ghcr.io/yakymivdanylo/fleet-management-api:1.0.0
docker pull ghcr.io/yakymivdanylo/fleet-management-api:1.1.0
```

### A3. Argo CD CLI (Windows)

Завантажити `argocd-windows-amd64.exe` зі сторінки релізів
(<https://github.com/argoproj/argo-cd/releases/latest>), перейменувати в `argocd.exe`, покласти в папку з PATH
(наприклад `C:\Users\dryak\bin`).

```bash
argocd version --client
```

---

## Частина B. Лайв-демонстрація

### B0. Піднімаємо кластер і Argo CD (п. 3)

```bash
minikube start
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd get pods -w          # чекаємо, поки всі поди Running (Ctrl+C)
```

**Пояснення.** Створюємо namespace `argocd` і ставимо офіційні маніфести Argo CD. `--server-side --force-conflicts`
потрібні, бо CRD Argo CD завеликі для звичайного `kubectl apply` (анотація `last-applied` перевищує ліміт).

Окремий термінал — доступ до інтерфейсу:

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
```

Основний термінал — вхід і зміна пароля:

```bash
argocd admin initial-password -n argocd                     # початковий пароль admin
argocd login localhost:8080 --username admin --insecure     # --insecure: самопідписаний сертифікат
argocd account update-password                              # змінюємо початковий пароль
kubectl -n argocd delete secret argocd-initial-admin-secret # початковий пароль більше не потрібен
```

Інтерфейс: <https://localhost:8080> (браузер попередить про сертифікат — продовжуємо).
Репозиторій публічний, тому `argocd repo add` **не потрібен**.

### B1. Секрет (паролі НЕ в Git) і єдиний ручний apply (п. 1, 4)

```bash
kubectl create namespace fleet
kubectl -n fleet create secret generic fleet-secret \
  --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 16)" \
  --from-literal=RABBITMQ_DEFAULT_USER=fleet \
  --from-literal=RABBITMQ_DEFAULT_PASS="$(openssl rand -hex 16)" \
  --from-literal=JWT_SECRET_KEY="$(openssl rand -hex 32)"
```

**Пояснення.** `values-minikube.yaml` містить `existingSecret: fleet-secret`: чарт не рендерить свій Secret, а поди
читають паролі з цього. Він створений руками, не з Git, тому Argo CD його не чіпає (навіть з `prune`) і паролі в
репозиторій не потрапляють. Чому це обов'язково: без `existingSecret` чарт генерує випадкові паролі через
`randAlphaNum`, а Argo CD лише рендерить шаблони (`lookup` у кластер не ходить) — кожна синхронізація давала б нові паролі.

```bash
kubectl apply -f bootstrap/root.yaml      # ЄДИНИЙ ручний apply
argocd app list
argocd app get fleet-management
kubectl -n fleet get pods
helm list -n fleet                        # порожньо: Helm лише рендерить шаблони, реліз не створює
```

**Пояснення.** `root` стежить за каталогом `argocd-apps/` і сам створює дочірній Application `fleet-management`
(App of Apps). Дочірній, своєю чергою, розгортає чарт у namespace `fleet`. Додати новий компонент надалі = додати
один файл в `argocd-apps/`.

### B2. Показати інтерфейс (п. 4)

<https://localhost:8080> → `root` → `fleet-management` → дерево об'єктів (Deployments, Services, ConfigMap, PVC, Pods).
Очікувано: **Synced / Healthy**. Для консолі:

```bash
argocd app get fleet-management          # Sync Status: Synced, Health Status: Healthy
kubectl -n fleet port-forward svc/fleet-management-api 8081:80     # окремий термінал
curl localhost:8081/version              # {"version":"1.0.0"}
```

### B3. Реліз комітом (п. 5)

```bash
sed -i 's/tag: "1.0.0"/tag: "1.1.0"/' charts/fleet-management/values-minikube.yaml   # змінює api і worker
git diff                                                                              # показати зміну
git commit -am "chore(infra): release fleet-management 1.1.0" && git push

argocd app get fleet-management --refresh      # не чекати опитування Git (до 3 хв)
kubectl -n fleet get pods -w                   # rolling update: нові поди підіймаються, старі зникають
curl localhost:8081/version                    # {"version":"1.1.0"}
```

**Пояснення.** Руками в кластері нічого не робимо — змінюється лише тег у Git. Argo CD бачить новий коміт
(`--refresh` форсує перевірку замість очікування poll-інтервалу), порівнює його з кластером (OutOfSync), автоматично
синхронізує, Deployment виконує rolling update (`maxUnavailable: 0` — без простою). Після оновлення подів старий
port-forward може обірватися — перезапустіть його. В інтерфейсі: кнопка *Refresh* → OutOfSync → автосинхронізація →
нові поди в дереві.

### B4. Дрейф і selfHeal (п. 6a)

Спершу **без** selfHeal:

```bash
kubectl -n fleet scale deployment fleet-management-api --replicas=5
argocd app get fleet-management          # Sync Status: OutOfSync, репліки лишаються 5
kubectl -n fleet get deploy fleet-management-api
```

**Пояснення.** `automated` без `selfHeal` синхронізує лише при **змінах у Git**. Ручна зміна кластера фіксується як
дрейф (OutOfSync), але не виправляється.

Тепер вмикаємо selfHeal — теж через Git (root сам застосує зміну Application):

```bash
sed -i 's/      prune: true.*/      prune: true\n      selfHeal: true/' argocd-apps/fleet-management.yaml
git diff
git commit -am "chore(infra): enable selfHeal for fleet-management" && git push
argocd app get root --refresh && argocd app get fleet-management --refresh

kubectl -n fleet scale deployment fleet-management-api --replicas=5
kubectl -n fleet get deploy fleet-management-api -w     # за кілька секунд знову 2/2
```

**Пояснення.** З `selfHeal: true` Argo CD не лише виявляє дрейф, а й повертає бажаний стан із Git (кількість реплік 2
із чарту).

### B5. Synced, але Degraded (п. 6b)

```bash
sed -i 's/tag: "1.1.0"/tag: "9.9.9"/' charts/fleet-management/values-minikube.yaml
git commit -am "chore(infra): deploy non-existent image tag 9.9.9" && git push

argocd app get fleet-management --refresh
#   Sync Status:   Synced        <- кластер ТОЧНО збігається з Git
#   Health Status: Progressing -> Degraded (через ~120 с, progressDeadlineSeconds)
kubectl -n fleet get pods                 # нові поди: ErrImagePull / ImagePullBackOff
curl localhost:8081/version               # досі 1.1.0 — старі поди обслуговують трафік
```

**Пояснення.** Це важлива різниця: **Sync** відповідає на питання «чи збігається кластер із Git?», **Health** — «чи
працює те, що розгорнуто?». Маніфест із неіснуючим тегом застосовано коректно (Synced), та образ не завантажити
(Degraded). Завдяки `maxUnavailable: 0` старі поди не вимкнено — користувачі не постраждали.

### B6. Відкат через `git revert` (п. 6c)

```bash
git log --oneline -5
git revert --no-edit HEAD                  # HEAD = коміт з 9.9.9 (або вкажіть його хеш)
git push

argocd app get fleet-management --refresh  # знову Synced / Healthy
argocd app history fleet-management        # кожна синхронізація прив'язана до коміту
git log --oneline -5
curl localhost:8081/version                # {"version":"1.1.0"}
```

**Пояснення.** Відкочуємо **опис**, а не кластер: `git revert` створює новий коміт, що скасовує зміну, і Argo CD
розгортає його. Історія лишається повною та аудитованою (`git log` + `argocd app history`). `argocd app rollback` тут
не підходить: він працює лише з вимкненою автосинхронізацією, інакше Argo CD одразу поверне стан із Git.

### B7. Якщо викладач просить змінити інше значення

Будь-яка зміна — тільки через Git, у `charts/fleet-management/values-minikube.yaml`:

```bash
# приклад: 3 репліки API
sed -i 's/^replicaCount: 2/replicaCount: 3/' charts/fleet-management/values-minikube.yaml
git commit -am "chore(infra): scale api to 3 replicas" && git push
argocd app get fleet-management --refresh
kubectl -n fleet get pods
```

Інші приклади: `config.appName` (змінює ConfigMap → rolling update завдяки `checksum/config`),
`resources.limits.memory`.

---

## Прибирання

```bash
argocd app delete root --cascade        # видаляє root, fleet-management і всі їхні об'єкти
kubectl delete namespace fleet argocd
minikube stop
```

## Типові проблеми

| Симптом | Причина / дія |
|---|---|
| `ImagePullBackOff` на тегах 1.0.0/1.1.0 | пакет GHCR приватний або тег не опубліковано (перевірити A1, A2) |
| Поди `CreateContainerConfigError` | не створено `fleet-secret` у namespace `fleet` (B1) |
| `ComparisonError ... repository not found` | помилка в `repoURL` |
| Зміна не приїхала | запушено не в `main` або не минув poll — `argocd app get ... --refresh` |
| `values-minikube.yaml: no such file` | `valueFiles` рахується від `path` чарту, не від кореня репозиторію |
