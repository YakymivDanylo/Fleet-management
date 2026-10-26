# Звіт: ЛР-5 «GitOps: розгортання проєкту через Argo CD»

Проєкт: Fleet Management (станційний каршерінг), репозиторій `YakymivDanylo/Fleet-management`.
Вихідні дані: Helm-чарт із ЛР-4, локальний minikube. Покрокові команди для захисту — у [`DEMO.md`](DEMO.md).

## 1. Мета та підхід

Перейти від ручного `helm upgrade --install` до GitOps: **бажаний стан кластера описаний у Git**, а Argo CD у кластері
сам приводить кластер до цього стану. Єдина ручна дія з об'єктами Argo CD — `kubectl apply -f bootstrap/root.yaml`.

Обрано **варіант (b)** із завдання — каталоги `bootstrap/`, `argocd-apps/`, `charts/` у репозиторії застосунку.
Обґрунтування: один репозиторій на навчальний проєкт, чарт уже живе поруч із кодом. Наслідок (і вимога завдання):
зміни конфігурації не мають перезбирати образ — додано `paths-ignore` у CI (див. п. 3).

## 2. Структура репозиторію конфігурації (п. 1)

```
bootstrap/root.yaml                            # root Application (ручний apply, один раз)
argocd-apps/fleet-management.yaml              # Application чарту, його підхоплює root
charts/fleet-management/                       # чарт із ЛР-4 (перенесено з chart/ через git mv — історія збережена)
charts/fleet-management/values-minikube.yaml   # значення для minikube (тег образу тощо)
```

Зміни в чарті порівняно з ЛР-4:

| Зміна | Навіщо |
|---|---|
| `existingSecret` (values, `_helpers.tpl`, `secret.yaml`) | якщо заданий — Secret не рендериться, усі поди читають паролі з Secret, створеного вручну; паролі не потрапляють у Git |
| `progressDeadlineSeconds` (Deployment API) | у minikube-значеннях 60 с замість 600 — зламаний реліз стає `Degraded` швидко, а не за 10 хв |
| `values-minikube.yaml` | `existingSecret: fleet-secret`, образи з GHCR, `hooks.preUpgrade.enabled: false` |
| `values.schema.json` | валідація нових параметрів |

**Секрети.** Чому `existingSecret` обов'язковий саме з Argo CD: чарт ЛР-4 генерував паролі через `randAlphaNum` і
зберігав їх стабільними через `lookup` наявного Secret. Argo CD лише **рендерить** шаблони (`helm template`) без доступу
`lookup` до кластера, тож кожна синхронізація згенерувала б нові паролі й зламала Postgres/RabbitMQ. Secret `fleet-secret`
створюється одноразово `kubectl create secret` із випадковими значеннями; Argo CD його не чіпає, бо його немає в Git
(навіть з `prune: true`).

**Pre-upgrade хук вимкнено.** Argo CD відображає Helm-хуки `pre-install`/`pre-upgrade` на фазу **PreSync**. Job
перевірки PostgreSQL з ЛР-4 запускався б *до* створення Postgres і провалив би першу синхронізацію. Готовність БД і
так гарантує init-контейнер `wait-for-postgres` у Deployment API.

## 3. Образ у реєстрі та версія (п. 2)

- Образи публікуються в **GHCR**: `ghcr.io/yakymivdanylo/fleet-management-api` і `...-worker`.
- CI (`.github/workflows/ci.yml`, job `publish`) тепер запускається і на тег `vX.Y.Z`: збирає образи з
  `--build-arg APP_VERSION=X.Y.Z` і пушить тег `X.Y.Z` (для `main` — як раніше `sha` та `latest`). Job залежить від усіх
  quality-gate'ів (тести, lint, складність, SCA, secrets, Trivy).
- `on.push.paths-ignore` для `bootstrap/**`, `argocd-apps/**`, `charts/**`, `docs/**` — коміт зі зміною тегу образу не
  запускає збірку (для тегових пушів фільтр шляхів не застосовується, тож реліз-тег усе одно збирає образ).
- Пакети GHCR потрібно один раз зробити **публічними**, інакше кластер отримає `ImagePullBackOff`.
- Версію застосунок показує ендпоінтом **`GET /version`** → `{"version": "1.1.0"}` (додано; тест у
  `tests/unit/test_info_endpoints.py`). Значення бере з `APP_VERSION`, вшитої в образ при збірці (`ARG APP_VERSION` у
  `Dockerfile` вже існував); `/info` також повертає версію.

## 4. Argo CD та Application (пп. 3–4)

- Argo CD у namespace `argocd` (`kubectl apply --server-side --force-conflicts -f .../stable/manifests/install.yaml`),
  CLI `argocd`, доступ через `port-forward svc/argocd-server 8080:443`, початковий пароль `admin` змінено,
  `argocd-initial-admin-secret` видалено. Репозиторій публічний — `argocd repo add` не потрібен.
- `argocd-apps/fleet-management.yaml`: `source.path: charts/fleet-management`, `valueFiles: values-minikube.yaml`
  (шлях відносно каталогу чарту), `syncPolicy.automated.prune: true`, `CreateNamespace=true`, ціль — namespace `fleet`.
  Ім'я Application = ім'я Helm-релізу, тому об'єкти називаються `fleet-management-api`, `fleet-management-postgres` тощо.
- `bootstrap/root.yaml` — **App of Apps**: стежить за каталогом `argocd-apps/` з `automated` + `prune` + `selfHeal`.
  Новий компонент (Argo Rollouts, моніторинг у ЛР-6/7) = один новий файл у `argocd-apps/`.

## 5. Оновлення, дрейф, Degraded, відкат (пп. 5–6)

| Сценарій | Дія | Очікуваний результат |
|---|---|---|
| Реліз (п. 5) | у `values-minikube.yaml` `1.0.0` → `1.1.0`, commit + push | OutOfSync → автосинхронізація → rolling update; `/version` = `1.1.0` |
| Дрейф без selfHeal (6a) | `kubectl scale ... --replicas=5` | `OutOfSync`, репліки лишаються 5 |
| Дрейф із selfHeal (6a) | `selfHeal: true` у `argocd-apps/fleet-management.yaml` + повторний scale | Argo CD повертає 2 репліки за секунди |
| Неіснуючий тег (6b) | тег `9.9.9` | `Synced`, але `Degraded` (поди `ImagePullBackOff`); старі поди тримають трафік (`maxUnavailable: 0`) |
| Відкат (6c) | `git revert` + push | `Synced / Healthy`, `/version` = `1.1.0`; історія в `git log` та `argocd app history` |

Ключове спостереження: **Sync ≠ Health.** Synced означає «кластер збігається з Git», Healthy — «розгорнуте працює». Помилка
в Git (неіснуючий тег) дає Synced + Degraded, і лікується не втручанням у кластер, а `git revert`.

## 6. Результати верифікації

Виконано локально (без кластера):

| Перевірка | Результат |
|---|---|
| `helm lint charts/fleet-management -f .../values-minikube.yaml` | 0 failed (лише INFO «icon is recommended») |
| `helm template` з `values-minikube.yaml` | Secret не рендериться; усі `secretKeyRef` → `fleet-secret`; образи `ghcr.io/yakymivdanylo/...:1.0.0` |
| `helm template` зі значеннями за замовчуванням | 1 Secret (поведінка ЛР-4 збережена) |
| `pytest tests/unit/test_info_endpoints.py` | 3 passed (включно з `/version`) |

Живий прогін на minikube (виконується студентом за `DEMO.md`; сюди вставляються виводи та скриншоти):

| № | Що зафіксувати | Статус |
|---|---|---|
| 1 | `kubectl -n argocd get pods` — Argo CD Running | ☐ |
| 2 | Інтерфейс: `root` → `fleet-management`, дерево, Synced / Healthy | ☐ |
| 3 | `argocd app list`, `helm list -n fleet` (порожньо) | ☐ |
| 4 | `curl /version` → `1.0.0`, після релізу → `1.1.0` | ☐ |
| 5 | `argocd app get` при OutOfSync (scale без selfHeal) | ☐ |
| 6 | Повернення реплік після увімкнення selfHeal | ☐ |
| 7 | Synced + Degraded, `kubectl get pods` з `ImagePullBackOff` | ☐ |
| 8 | `git log --oneline`, `argocd app history fleet-management` після revert | ☐ |

## 7. Висновки

GitOps прибирає «дрейф знань»: що працює в кластері, видно з `git log`; кожне розгортання прив'язане до коміту й
відтворюване; відкат — звичайний `git revert`. Ціна: потрібна окрема політика секретів (тут — `existingSecret`;
для production доцільні Sealed Secrets / SOPS / External Secrets) і дисципліна «в кластері руками не змінюємо» — її
забезпечує `selfHeal`. У реальному проєкті коміт зі зміною тегу робить CI після збірки образу.
