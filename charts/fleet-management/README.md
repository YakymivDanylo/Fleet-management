# Helm-чарт `fleet-management`

Чарт розгортає той самий застосунок, що й маніфести `k8s/` з лабораторної №3: FastAPI API (Deployment + Service + опційний Ingress), telemetry worker, PostgreSQL, Redis і RabbitMQ (Deployment + Service, для Postgres і RabbitMQ — PVC), ConfigMap та Secret.

## `version` та `appVersion`

| Поле | Значення | Що означає для цього проєкту |
|---|---|---|
| `version` | `0.1.0` | Версія **самого чарта** (шаблони, `values.yaml`, структура). Змінюється, коли ми правимо шаблони чи значення за замовчуванням. Підпорядковується SemVer. |
| `appVersion` | `1.0.0` | Версія **застосунку**, який пакуємо (образ `fleet-management-api`). Інформаційне поле й значення за замовчуванням для тега образу, якщо `image.tag` порожній. |

Вони змінюються незалежно: вихід образу `1.1.0` без змін у шаблонах не вимагає нової `version` (достатньо `--set image.tag=1.1.0`), а виправлення помилки в шаблоні підвищує `version`, залишаючи `appVersion` незмінним.

## Встановлення

Передумови: minikube з надбудовою `ingress`, образи `fleet-management-api:1.0.0`, `fleet-management-api:1.1.0`, `fleet-management-worker:1.0.0` завантажені в кластер (`minikube image load ...`, див. кореневий README).

```powershell
# dev (значення за замовчуванням + values-dev.yaml)
helm install fleet charts/fleet-management -n fleet-management --create-namespace -f charts/fleet-management/values-dev.yaml

# prod (3 репліки, образ 1.1.0, Ingress)
helm install fleet charts/fleet-management -n fleet-management --create-namespace -f charts/fleet-management/values-prod.yaml
```

Паролі у файлах значень **не зберігаються**. Якщо `secret.*` порожні, чарт повторно використовує значення з уже наявного Secret, а при першому встановленні генерує випадкові. Задати власні:

```powershell
helm install fleet charts/fleet-management -n fleet-management --create-namespace `
  --set secret.postgresPassword=$env:PG_PASS --set secret.rabbitmqPassword=$env:MQ_PASS --set secret.jwtSecretKey=$env:JWT_KEY
```

Життєвий цикл і перевірка:

```powershell
helm lint charts/fleet-management
helm template fleet charts/fleet-management -f charts/fleet-management/values-prod.yaml   # без кластера
helm upgrade fleet charts/fleet-management -n fleet-management --set image.tag=1.1.0
helm history fleet -n fleet-management
helm rollback fleet 2 -n fleet-management
helm test fleet -n fleet-management
helm uninstall fleet -n fleet-management
```

### Пріоритет значень

`values.yaml` чарта < файли `-f` (кожен наступний перекриває попередній) < `--set` / `--set-string` (найвищий). Приклад у [звіті](../../docs/lab4-helm/REPORT.md).

## Параметри `values.yaml`

| Параметр | Опис | За замовчуванням |
|---|---|---|
| `nameOverride`, `fullnameOverride` | Перевизначення імені чарта / повного імені об'єктів | `""` |
| `replicaCount` | Кількість реплік API | `2` |
| `image.repository` / `image.tag` | Образ API; порожній `tag` → `appVersion` | `fleet-management-api` / `1.0.0` |
| `image.pullPolicy` | Політика завантаження образів API та worker | `IfNotPresent` |
| `service.type` | Тип Service API (`ClusterIP`/`NodePort`/`LoadBalancer`) | `NodePort` |
| `service.port` | Порт Service API | `80` |
| `service.nodePort` | Фіксований NodePort; `null` — призначає кластер (чарт можна встановити двічі) | `null` |
| `ingress.enabled` | Створити Ingress | `false` |
| `ingress.className` / `host` / `path` / `annotations` | Параметри Ingress | `nginx` / `fleet.local` / `/` / `{}` |
| `resources` | requests/limits API | `100m/128Mi` / `500m/256Mi` |
| `worker.replicaCount`, `worker.image.*`, `worker.resources` | Worker телеметрії | `1`, `fleet-management-worker:1.0.0` |
| `postgres.replicaCount`, `postgres.image.*`, `postgres.resources` | PostgreSQL | `1`, `postgres:16` |
| `postgres.persistence.enabled` | PVC для даних (інакше `emptyDir`) | `true` |
| `postgres.persistence.size` / `storageClass` / `accessMode` | Параметри PVC | `1Gi` / `""` / `ReadWriteOnce` |
| `redis.replicaCount`, `redis.image.*`, `redis.resources` | Redis | `1`, `redis:7-alpine` |
| `rabbitmq.replicaCount`, `rabbitmq.image.*`, `rabbitmq.resources` | RabbitMQ | `1`, `rabbitmq:4-management-alpine` |
| `rabbitmq.persistence.*` | PVC RabbitMQ (як у Postgres) | `true`, `1Gi` |
| `config.appName` | `APP_NAME` — назва в `/info` та OpenAPI | `Fleet Management (dev)` |
| `config.telemetryQueue` | Черга RabbitMQ для worker | `telemetry` |
| `config.resilienceEnabled` | Таймаути й повтори запитів до Redis | `true` |
| `config.accessTokenExpireMinutes` | Час життя JWT | `30` |
| `config.postgresDb` / `config.postgresUser` | Назва БД та користувач | `fleet_management` / `fleet_user` |
| `secret.postgresPassword` | Пароль БД; порожній → існуючий або випадковий | `""` |
| `secret.rabbitmqUser` | Користувач RabbitMQ | `fleet` |
| `secret.rabbitmqPassword` | Пароль RabbitMQ; порожній → існуючий або випадковий | `""` |
| `secret.jwtSecretKey` | Ключ підпису JWT; порожній → існуючий або випадковий | `""` |
| `hooks.preUpgrade.enabled` | Job-хук `pre-upgrade`, що перевіряє доступність PostgreSQL | `true` |

Відмінності середовищ: [`values-dev.yaml`](values-dev.yaml) (1 репліка, малі ресурси, образ 1.0.0, без Ingress) і [`values-prod.yaml`](values-prod.yaml) (3 репліки, більші ресурси, образ 1.1.0, Ingress `fleet.local`).

## Структура

```
charts/fleet-management/
├── Chart.yaml            values.yaml   values-dev.yaml   values-prod.yaml   values.schema.json
└── templates/
    ├── _helpers.tpl                      # імена, мітки, образ, генерація секретів
    ├── NOTES.txt                         # підказка після встановлення
    ├── configmap.yaml  secret.yaml
    ├── postgres-{pvc,deployment,service}.yaml   rabbitmq-{pvc,deployment,service}.yaml
    ├── redis-{deployment,service}.yaml   worker-deployment.yaml
    ├── api-{deployment,service,ingress}.yaml
    ├── hooks/pre-upgrade-job.yaml        # helm.sh/hook: pre-upgrade
    └── tests/test-api.yaml               # helm test: GET /health та /info
```
