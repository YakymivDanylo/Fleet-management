# Звіт: Лабораторна робота №3 — Розгортання власного застосунку в Kubernetes

**Застосунок:** Fleet Management (каршерінг) — FastAPI API + telemetry worker, PostgreSQL, Redis, RabbitMQ
**Гілка:** `feat/lab3-kubernetes`
**Дата виконання:** 2026-10-06

Усі команди виконано на реальному кластері; повний вивід кожного кроку збережено в каталозі [`outputs/`](outputs/).
Пояснення прийнятих рішень та термінології — у файлі [`EXPLANATION.md`](EXPLANATION.md).

---

## Середовище

| Компонент | Версія |
|---|---|
| ОС хоста | Windows 11 Home (WSL2) |
| minikube | v1.39.0, драйвер `docker` |
| Kubernetes (сервер) | v1.37.0, runtime `containerd 2.3.4` |
| kubectl (клієнт) | v1.36.1 |
| Ресурси вузла | 4 CPU, 6 GiB RAM |

## Архітектура розгортання

```mermaid
flowchart LR
    user([Браузер / curl]) -->|Host: fleet.local| ing[Ingress api<br/>nginx]
    user -.->|NodePort 30080| svcapi
    ing --> svcapi[Service api<br/>NodePort]
    svcapi --> api1[Pod api]
    svcapi --> api2[Pod api]
    api1 & api2 --> svcpg[Service postgres] --> pg[(Pod postgres<br/>PVC postgres-data)]
    api1 & api2 --> svcredis[Service redis] --> redis[(Pod redis)]
    worker[Pod worker] --> svcmq[Service rabbitmq] --> mq[(Pod rabbitmq<br/>PVC rabbitmq-data)]
    worker --> svcpg
    worker --> svcredis
    cm[[ConfigMap fleet-config]] -.-> api1 & api2 & worker & pg
    sec[[Secret fleet-secret]] -.-> api1 & api2 & worker & pg & mq
```

Усі об'єкти — у namespace `fleet-management`.

## Маніфести `k8s/`

| Файл | Об'єкт | Призначення |
|---|---|---|
| `00-namespace.yaml` | Namespace `fleet-management` | Ізоляція об'єктів проєкту |
| `01-configmap.yaml` | ConfigMap `fleet-config` | 7 несекретних параметрів |
| `02-secret.yaml` | Secret `fleet-secret` | 4 чутливі параметри (лабораторні значення) |
| `10-postgres-pvc.yaml` | PVC `postgres-data` (1Gi, RWO) | Постійні дані БД |
| `11-postgres-deployment.yaml` | Deployment `postgres` | PostgreSQL 16 |
| `12-postgres-service.yaml` | Service `postgres` (ClusterIP) | DNS-ім'я для БД |
| `20-redis-deployment.yaml` | Deployment `redis` | Кеш стану авто |
| `21-redis-service.yaml` | Service `redis` (ClusterIP) | DNS-ім'я для кешу |
| `30-rabbitmq-pvc.yaml` | PVC `rabbitmq-data` (1Gi, RWO) | Постійні дані черги |
| `31-rabbitmq-deployment.yaml` | Deployment `rabbitmq` | Брокер повідомлень телеметрії |
| `32-rabbitmq-service.yaml` | Service `rabbitmq` (ClusterIP) | AMQP 5672 + панель 15672 |
| `40-api-deployment.yaml` | Deployment `api` (2 репліки) | Основний застосунок |
| `41-api-service.yaml` | Service `api` (NodePort 30080) | Доступ у кластері та з хоста |
| `42-api-ingress.yaml` | Ingress `api` (`fleet.local`) | HTTP-вхід через nginx |
| `50-worker-deployment.yaml` | Deployment `worker` | Обробник черги телеметрії |

### Параметри ConfigMap `fleet-config`

| Ключ | Значення | Призначення |
|---|---|---|
| `APP_NAME` | `Fleet Management (k8s)` | Назва застосунку (видно в `/info`, `/docs`) |
| `REDIS_URL` | `redis://redis:6379/0` | Підключення до Redis |
| `TELEMETRY_QUEUE` | `telemetry` | Черга, яку обробляє worker |
| `RESILIENCE_ENABLED` | `true` | Таймаути/повтори до Redis |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Час життя JWT |
| `POSTGRES_DB` | `fleet_management` | Назва БД |
| `POSTGRES_USER` | `fleet_user` | Користувач БД |

### Параметри Secret `fleet-secret`

Значення використовуються лише в лабораторній роботі й не пов'язані з робочими системами.

| Ключ | Призначення |
|---|---|
| `POSTGRES_PASSWORD` | Пароль БД; з нього складається `DATABASE_URL` |
| `RABBITMQ_DEFAULT_USER` / `RABBITMQ_DEFAULT_PASS` | Облікові дані брокера; з них складається `RABBITMQ_URL` |
| `JWT_SECRET_KEY` | Ключ підпису access-токенів |

## Зміни в коді застосунку

| Файл | Зміна | Навіщо |
|---|---|---|
| `src/fleet_management/main.py` | Ендпоінти `/livez` і `/info` | Liveness-проба без залежностей; показ версії та імені пода (пункти 6b, 6c) |
| `src/fleet_management/config.py` | Поле `app_version` | Версія з оточення |
| `Dockerfile` | `ARG/ENV APP_VERSION` | Версія «запікається» в образ при збірці |
| `alembic/env.py` | `pg_advisory_lock` перед міграціями | Кілька реплік не мігрують БД одночасно |
| `tests/unit/test_info_endpoints.py` | 2 тести | Контракт нових ендпоінтів |

---

## 1. Підготовка образу

Вивід: [`outputs/01-images.txt`](outputs/01-images.txt)

```text
fleet-management-worker   1.0.0   6aa765679e8d   310MB
fleet-management-api      1.0.0   b0f35d5ee812   310MB
fleet-management-api      1.1.0   6c3853af1ff7   310MB

fleet-management-api:1.0.0 APP_VERSION=1.0.0
fleet-management-api:1.1.0 APP_VERSION=1.1.0

$ minikube image ls | grep fleet
docker.io/library/fleet-management-worker:1.0.0
docker.io/library/fleet-management-api:1.1.0
docker.io/library/fleet-management-api:1.0.0
```

- a) використано образи власного проєкту (ті самі `Dockerfile` / `Dockerfile.worker`, що в Лабах 1–2);
- b) образи завантажено в minikube (`minikube image load`);
- c) теги — конкретні версії, `latest` не використовується;
- d) підготовлено дві версії API — `1.0.0` і `1.1.0`; версія вбудована в образ і повертається ендпоінтом `/info`.

## 2. Локальний кластер

Вивід: [`outputs/02-cluster.txt`](outputs/02-cluster.txt)

```text
NAME       STATUS   ROLES           VERSION   CONTAINER-RUNTIME
minikube   Ready    control-plane   v1.37.0   containerd://2.3.4

coredns, etcd, kindnet, kube-apiserver, kube-controller-manager,
kube-proxy, kube-scheduler, metrics-server, storage-provisioner  — усі 1/1 Running

ingress              enabled ✅
metrics-server       enabled ✅
storage-provisioner  enabled ✅
```

## 3. Namespace проєкту

Namespace `fleet-management` (за назвою проєкту) описано в `k8s/00-namespace.yaml`. Кожен інший маніфест явно містить `namespace: fleet-management`, тому всі об'єкти створюються лише в ньому.

## 4. Маніфести

Відповідність вимогам:

| Вимога | Реалізація |
|---|---|
| a) каталог `k8s/`, по файлу на об'єкт | 15 файлів, числові префікси задають порядок застосування |
| b) Deployment: ≥2 репліки, labels/selector, requests/limits, проби | `api`: `replicas: 2`; selector `app.kubernetes.io/name: api` збігається з labels шаблону; `requests 100m/128Mi`, `limits 500m/256Mi`; `startupProbe` + `livenessProbe` (`/livez`) + `readinessProbe` (`/health`) |
| c) Service для доступу в кластері та з хоста | `api` типу `NodePort` (ClusterIP всередині + порт 30080 на вузлі) |
| d) ConfigMap ≥2 параметри | 7 параметрів, підключено через `envFrom` |
| e) Secret ≥1 чутливий параметр | 4 параметри, підключено через `secretKeyRef` |
| f) Ingress або NodePort | Обидва: Ingress `fleet.local` + NodePort 30080 |
| g) PVC для компонентів зі станом | `postgres-data` (БД), `rabbitmq-data` (черга) |

## 5. Розгортання

### 5a. Застосування однією командою

Вивід: [`outputs/05a-apply.txt`](outputs/05a-apply.txt)

```text
$ kubectl apply -f k8s/
namespace/fleet-management created
configmap/fleet-config created
secret/fleet-secret created
persistentvolumeclaim/postgres-data created
deployment.apps/postgres created
...
ingress.networking.k8s.io/api created
deployment.apps/worker created
```

### 5b. Створені об'єкти

Вивід: [`outputs/05b-objects.txt`](outputs/05b-objects.txt)

```text
NAME                        READY   STATUS    RESTARTS   AGE
api-6cdb7b775d-7rplf        1/1     Running   0          37s
api-6cdb7b775d-jlxqr        1/1     Running   0          37s
postgres-5999845566-g9tgk   1/1     Running   0          37s
rabbitmq-59b6ccb856-8spvn   1/1     Running   0          37s
redis-6dcd67b5f7-p5t79      1/1     Running   0          37s
worker-776fcddd6-b2qhw      1/1     Running   0          37s

deployment.apps/api   2/2   ...   fleet-management-api:1.0.0
replicaset.apps/api-6cdb7b775d   2   2   2   ...   pod-template-hash=6cdb7b775d

service/api        NodePort    10.103.247.101   80:30080/TCP
service/postgres   ClusterIP   10.109.23.130    5432/TCP
service/rabbitmq   ClusterIP   10.109.94.123    5672/TCP,15672/TCP
service/redis      ClusterIP   10.105.141.237   6379/TCP

persistentvolumeclaim/postgres-data   Bound   1Gi   RWO   standard
persistentvolumeclaim/rabbitmq-data   Bound   1Gi   RWO   standard
```

Ієрархія: Deployment `api` → ReplicaSet `api-6cdb7b775d` (хеш шаблону пода) → Pods `api-6cdb7b775d-*`.

**Захист міграцій** ([`outputs/05-migrations-lock.txt`](outputs/05-migrations-lock.txt)): обидві репліки стартували одночасно, але міграції виконав лише один под; другий дочекався advisory lock і побачив, що схема вже актуальна. Перезапусків — 0.

```text
pod/api-6cdb7b775d-7rplf:
  Running upgrade  -> 945d8fb7f540, initial schema
  Running upgrade 945d8fb7f540 -> d9c208b5f3b7, add telemetry readings
  Running upgrade d9c208b5f3b7 -> b7e4a1c2d3f5, add users
pod/api-6cdb7b775d-jlxqr:
  (міграцій немає) Application startup complete.
```

### 5c. Застосунок працює

Вивід: [`outputs/05c-access.txt`](outputs/05c-access.txt)

Перевірено три шляхи доступу:

| Шлях | Команда | Результат |
|---|---|---|
| Ingress (`fleet.local`) | `curl -H 'Host: fleet.local' http://127.0.0.1:8080/info` | `{"app":"Fleet Management (k8s)","version":"1.0.0","pod":"api-6cdb7b775d-7rplf"}` |
| NodePort | `minikube ssh -- curl http://localhost:30080/info` | та сама відповідь |
| DNS всередині кластера | `kubectl run curl-test ... curl http://api.fleet-management.svc.cluster.local/info` | та сама відповідь |

Додатково: `/health` → `{"status":"ok","db":"connected"}`, `/docs` → HTTP 200; запит без заголовка `Host: fleet.local` → HTTP 404, тобто маршрутизацію справді виконує Ingress-правило.

Перевірено бізнес-логіку з записом у БД: `POST /auth/register` створив користувача (`id: 1`), `POST /auth/login` видав JWT, `GET /auth/me` з цим токеном повернув профіль.

> Під час автоматизованого прогону доступ до Ingress-контролера виконано через `kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 8080:80` (шлях запиту той самий: nginx → Ingress → Service → Pod).

**Перевірка в браузері.** Запущено `minikube tunnel` (у звичайному терміналі; прав адміністратора він не потребує) і додано рядок `127.0.0.1 fleet.local` у `C:\Windows\System32\drivers\etc\hosts` — щоб браузер знав, що вигадане ім'я `fleet.local` веде на локальний тунель.

Swagger UI застосунку за адресою http://fleet.local/docs — заголовок `Fleet Management (k8s)` береться з ConfigMap:

![Swagger UI через Ingress](screenshots/05c-browser-docs.png)

Два послідовні запити до http://fleet.local/info обслужили **різні поди** (`api-6cdb7b775d-sj28s` і `api-6cdb7b775d-x6kwh`) — Ingress розподіляє трафік між репліками:

| Запит 1 | Запит 2 |
|---|---|
| ![/info — под sj28s](screenshots/05c-browser-info-pod1.png) | ![/info — под x6kwh](screenshots/05c-browser-info-pod2.png) |

### 5d. Значення ConfigMap і Secret у контейнері

Вивід: [`outputs/05d-config-secret.txt`](outputs/05d-config-secret.txt)

```text
$ kubectl exec deploy/api -c api -- printenv APP_NAME REDIS_URL TELEMETRY_QUEUE RESILIENCE_ENABLED ...
Fleet Management (k8s)
redis://redis:6379/0
telemetry
true
30
fleet_management
fleet_user

$ kubectl describe pod -l app.kubernetes.io/name=api
    Environment Variables from:
      fleet-config  ConfigMap  Optional: false
    Environment:
      POSTGRES_PASSWORD:  <set to the key 'POSTGRES_PASSWORD' in secret 'fleet-secret'>
      JWT_SECRET_KEY:     <set to the key 'JWT_SECRET_KEY' in secret 'fleet-secret'>
      DATABASE_URL:       postgresql+asyncpg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@postgres:5432/$(POSTGRES_DB)
```

Значення з Secret у контейнері підтверджуються функціонально: застосунок не стартує без `JWT_SECRET_KEY` (перевірка в `lifespan`), видає та перевіряє JWT, а підключення до БД з паролем із Secret успішне (`"db":"connected"`).

## 6. Керування життєвим циклом

### 6a. Самовідновлення

Вивід: [`outputs/06a-self-healing.txt`](outputs/06a-self-healing.txt)

```text
$ kubectl delete pod api-6cdb7b775d-7rplf --wait=false
$ kubectl get pods -l app.kubernetes.io/name=api
api-6cdb7b775d-7rplf   1/1   Terminating   0   2m6s
api-6cdb7b775d-j9svb   0/1   Init:0/1      0   0s      ← новий под створено одразу
api-6cdb7b775d-jlxqr   1/1   Running       0   2m6s
...
api-6cdb7b775d-j9svb   1/1   Running       0   13s
api-6cdb7b775d-jlxqr   1/1   Running       0   2m19s

replicaset/api-6cdb7b775d   Created pod: api-6cdb7b775d-j9svb
```

ReplicaSet виявив розбіжність «бажано 2 — є 1» і створив новий под з іншим ім'ям.

### 6b. Масштабування і розподіл трафіку

Вивід: [`outputs/06b-scaling.txt`](outputs/06b-scaling.txt)

```text
$ kubectl scale deployment/api --replicas=4
api    4/4     4            4

40 запитів до /info через Ingress:
     10 api-6cdb7b775d-bp9ts
      8 api-6cdb7b775d-j9svb
     11 api-6cdb7b775d-jlxqr
     11 api-6cdb7b775d-xtsmf
```

Трафік рівномірно розподіляється між чотирма подами (ingress-nginx, round-robin).

### 6c. Rolling update до версії 1.1.0

Вивід: [`outputs/06c-rolling-update.txt`](outputs/06c-rolling-update.txt)

```text
$ kubectl set image deployment/api api=fleet-management-api:1.1.0
$ kubectl rollout status deployment/api
Waiting for deployment "api" rollout to finish: 1 out of 4 new replicas have been updated...
Waiting for deployment "api" rollout to finish: 2 out of 4 new replicas have been updated...
Waiting for deployment "api" rollout to finish: 3 out of 4 new replicas have been updated...
Waiting for deployment "api" rollout to finish: 1 old replicas are pending termination...
deployment "api" successfully rolled out

api-6cdb7b775d   0   0   0   fleet-management-api:1.0.0
api-7f77fc476c   4   4   4   fleet-management-api:1.1.0

Events:
  Scaled up replica set api-7f77fc476c from 0 to 1
  Scaled down replica set api-6cdb7b775d from 4 to 3
  Scaled up replica set api-7f77fc476c from 1 to 2
  Scaled down replica set api-6cdb7b775d from 3 to 2
  ...
  Scaled down replica set api-6cdb7b775d from 1 to 0
```

Заміна відбувалася по одному поду (`maxSurge: 1`, `maxUnavailable: 0`); старий ReplicaSet збережено з 0 реплік для відкату.

### 6d. Історія оновлень і відкат

Вивід: [`outputs/06d-history-rollback.txt`](outputs/06d-history-rollback.txt)

```text
$ kubectl rollout history deployment/api
REVISION  CHANGE-CAUSE
1         deploy 1.0.0
2         upgrade to 1.1.0

$ kubectl rollout undo deployment/api --to-revision=1
deployment.apps/api rolled back

$ kubectl rollout history deployment/api
REVISION  CHANGE-CAUSE
2         upgrade to 1.1.0
3         deploy 1.0.0

api-6cdb7b775d   4   4   4   fleet-management-api:1.0.0   ← повторно використано старий ReplicaSet
api-7f77fc476c   0   0   0   fleet-management-api:1.1.0

$ curl .../info
{"app":"Fleet Management (k8s)","version":"1.0.0","pod":"api-6cdb7b775d-6b4nl"}
```

Відкат виконано як ще один rolling update до шаблону ревізії 1; ревізія 1 отримала новий номер 3.

### 6e. Доступність під час оновлення

Вивід: [`outputs/06e-availability-summary.txt`](outputs/06e-availability-summary.txt), повний журнал — [`outputs/06e-availability-monitor.log`](outputs/06e-availability-monitor.log)

Монітор надсилав `GET /info` через Ingress кожні ~0,2 с (таймаут 2 с) протягом оновлення 1.0.0 → 1.1.0 **і** відкату:

```text
total requests: 458
HTTP 200: 458
failures: 0

responses per version:
    341 1.0.0
    117 1.1.0
```

Під час переходу відповіді версій чергувались (`1.0.0`, `1.1.0`, `1.0.0`, …) — одночасно працювали поди обох версій, і жоден запит не завершився помилкою.

## 7. Діагностика

### 7a. ImagePullBackOff

Вивід: [`outputs/07a-imagepullbackoff.txt`](outputs/07a-imagepullbackoff.txt)

```text
$ kubectl set image deployment/api api=fleet-management-api:9.9.9
$ kubectl get pods -l app.kubernetes.io/name=api
api-6cdb7b775d-6b4nl   1/1   Running            0   3m6s
api-6cdb7b775d-6lqmd   1/1   Running            0   3m
api-6cdb7b775d-j6jnx   1/1   Running            0   2m45s
api-6cdb7b775d-t2t8k   1/1   Running            0   2m54s
api-798f45f9f8-7lj74   0/1   ImagePullBackOff   0   45s

$ kubectl get deployment api
api    4/4     1            4
```

Завдяки `maxUnavailable: 0` жоден старий под не видалено: новий под не став Ready, тому rollout зупинився, а застосунок продовжив працювати. Монітор під час цього кроку: **325 з 325 запитів успішні** ([`outputs/07-availability-summary.txt`](outputs/07-availability-summary.txt)).

### 7b. Причина через describe та Events

Вивід: [`outputs/07b-describe-events.txt`](outputs/07b-describe-events.txt)

```text
    Image:          fleet-management-api:9.9.9
    State:          Waiting
      Reason:       ErrImagePull

Events:
  Normal   Pulling   kubelet  Pulling image "fleet-management-api:9.9.9"
  Warning  Failed    kubelet  Failed to pull image "fleet-management-api:9.9.9": ... failed to resolve reference
           "docker.io/library/fleet-management-api:9.9.9": pull access denied, repository does not exist ...
  Warning  Failed    kubelet  Error: ErrImagePull
  Normal   BackOff   kubelet  Back-off pulling image "fleet-management-api:9.9.9"
  Warning  Failed    kubelet  Error: ImagePullBackOff
```

Причина: тегу `9.9.9` немає локально у вузлі, тому kubelet шукає образ у Docker Hub, де такого репозиторію не існує. `ErrImagePull` → повторні спроби з наростаючою паузою → `ImagePullBackOff`.

### 7c. Логи та вхід у контейнер

Вивід: [`outputs/07c-logs-exec.txt`](outputs/07c-logs-exec.txt)

```text
$ kubectl logs api-798f45f9f8-7lj74 -c api
Error from server (BadRequest): container "api" ... is waiting to start: image can't be pulled

$ kubectl logs api-6cdb7b775d-6b4nl -c wait-for-postgres
postgres:5432 - accepting connections

$ kubectl logs api-6cdb7b775d-6b4nl -c api --tail=8
INFO:     10.244.0.4:57582 - "GET /info HTTP/1.1" 200 OK
INFO:     10.244.0.1:55002 - "GET /health HTTP/1.1" 200 OK
...

$ kubectl logs deploy/worker --tail=5
WARNING telemetry.worker: RabbitMQ not ready (attempt 7/10): Connect call failed
INFO telemetry.worker: Consuming queue 'telemetry'

$ kubectl exec -i api-6cdb7b775d-6b4nl -c api -- sh
whoami: uid=1000(appuser) gid=1000(appuser) groups=1000(appuser)
hostname: api-6cdb7b775d-6b4nl
APP_VERSION=1.0.0 APP_NAME=Fleet Management (k8s)
{"status":"ok","db":"connected"}
10.109.23.130 10.105.141.237 10.109.94.123     ← DNS-імена postgres, redis, rabbitmq → IP їхніх Service
```

У пода з `ImagePullBackOff` логів немає — контейнер не запускався, тому причину шукаємо в Events, а не в логах. Логи worker показують, що він дочекався готовності RabbitMQ і почав обробляти чергу. Усередині контейнера процес працює від непривілейованого користувача, видно ім'я пода, версію з образу та ConfigMap, а DNS-імена сервісів резолвляться в їхні ClusterIP.

> Інтерактивна сесія для демонстрації: `kubectl exec -it deploy/api -c api -- sh`.

### 7d. Виправлення

Вивід: [`outputs/07d-fix.txt`](outputs/07d-fix.txt)

```text
$ kubectl rollout undo deployment/api
deployment.apps/api rolled back
$ kubectl rollout status deployment/api
deployment "api" successfully rolled out

api-6cdb7b775d-6b4nl   1/1   Running   0   3m31s
api-6cdb7b775d-6lqmd   1/1   Running   0   3m25s
api-6cdb7b775d-j6jnx   1/1   Running   0   3m10s
api-6cdb7b775d-t2t8k   1/1   Running   0   3m19s

api-798f45f9f8   0   0   0     ← ReplicaSet з битим образом зменшено до 0
```

Робочі поди не перезапускались (вік не скинувся) — під час збою вони не зупинялись.

### Додатково: реальна проблема, знайдена під час розгортання

Вивід: [`outputs/00-real-issue-init-container.txt`](outputs/00-real-issue-init-container.txt)

Під час першого розгортання поди `api` залишались у стані `Init:0/1`, хоча Postgres був `Running`:

```text
$ kubectl logs pod/api-... -c wait-for-postgres
postgres:5432 - no attempt
waiting for postgres

$ kubectl exec pod/api-... -c wait-for-postgres -- sh -c 'id; pg_isready ...; pg_isready ... -U fleet_user'
uid=1000 gid=0(root) groups=0(root)
postgres:5432 - no attempt          exit=3
postgres:5432 - accepting connections   exit=0
```

**Причина:** под запускається з `runAsUser: 1000`, а в образі `postgres:16` користувача з UID 1000 немає. Без параметра `-U` утиліта `pg_isready` не може визначити ім'я користувача і завершується кодом 3 («спроба не виконувалась»), тому цикл очікування ніколи не завершувався.
**Виправлення:** init-контейнер отримує `POSTGRES_USER` з ConfigMap і викликає `pg_isready -U "$POSTGRES_USER"`. Після цього весь стек піднімається приблизно за 25 секунд.

## 8. Результати

### Розгортання з нуля однією командою

Вивід: [`outputs/08-from-scratch.txt`](outputs/08-from-scratch.txt)

```text
$ kubectl delete namespace fleet-management
$ kubectl get namespace fleet-management
Error from server (NotFound): namespaces "fleet-management" not found

$ kubectl apply -f k8s/
... 15 об'єктів created
# all deployments Available after 25 s

api-6cdb7b775d-sj28s        1/1   Running   0   24s
api-6cdb7b775d-x6kwh        1/1   Running   0   24s
postgres-5999845566-hnmzq   1/1   Running   0   24s
rabbitmq-59b6ccb856-vhgbh   1/1   Running   0   24s
redis-6dcd67b5f7-jcd7x      1/1   Running   0   24s
worker-776fcddd6-8m49m      1/1   Running   0   24s

ingress.networking.k8s.io/api   nginx   fleet.local   192.168.49.2   80
```

### Відповідність вимогам до здачі

| Вимога | Стан |
|---|---|
| Каталог `k8s/` закомічено в репозиторій | ✅ |
| README описує порядок розгортання та параметри ConfigMap/Secret | ✅ розділ «Розгортання в Kubernetes (minikube)» |
| Звіт з виводом команд для пунктів 5–7 | ✅ цей файл + `outputs/` |
| Маніфести написані вручну, не згенеровані `kubectl create -o yaml` | ✅ |
| Секрети не містять реальних паролів | ✅ лише лабораторні значення; gitleaks — `no leaks found` |
| Розгортання з нуля однією командою з `k8s/` | ✅ 25 с, 0 перезапусків |

## Висновки

1. Застосунок Fleet Management (5 компонентів) описано 15 декларативними маніфестами й розгорнуто в minikube однією командою `kubectl apply -f k8s/`.
2. Конфігурацію відокремлено від образу: несекретні параметри — у ConfigMap, чутливі — у Secret; рядки підключення складаються з них засобами Kubernetes (`$(VAR)`), без дублювання паролів.
3. Розділення проб (startup / readiness на `/health` з БД / liveness на `/livez` без залежностей) разом зі стратегією `maxSurge: 1, maxUnavailable: 0` і `preStop` забезпечили оновлення та відкат без жодної втраченої відповіді (458/458 і 325/325 запитів).
4. Невдале оновлення (неіснуючий тег) не вплинуло на користувачів: rollout зупинився на першому поді, причину знайдено через Events, виправлення — одна команда `rollout undo`.
5. Під час роботи виявлено й виправлено дві проблеми, які не проявляються в docker-compose: одночасні міграції кількох реплік (advisory lock) та несумісність `runAsUser` з `pg_isready` в init-контейнері.
