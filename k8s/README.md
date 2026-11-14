# `k8s/` — DEPRECATED

> **Статус: deprecated з 2026-11-14** (аудит документації ЛР№10, [ADR-0002](../docs/architecture/adr/0002-gitops-argo-canary-delivery.md)).
> Ці «сирі» маніфести (ЛР№3 DevOps) замінені Helm-чартом [`charts/fleet-management`](../charts/fleet-management/README.md),
> який розгортає Argo CD. Вони не містять canary-Rollout, моніторингу та `existingSecret` і не оновлюються.
> Актуальна топологія — [ISD §2.2](../docs/isd.md#isd-k8s). Каталог буде видалено після захисту курсу.

Нижче — опис у тому вигляді, в якому він був у кореневому README.

## Розгортання в Kubernetes (minikube) — історичний опис

Маніфести лежать у каталозі `k8s/` — по одному файлу на об'єкт. Числові префікси задають порядок застосування: спершу namespace, потім конфігурація, далі Postgres (`1x`), Redis (`2x`), RabbitMQ (`3x`), API (`4x`) і worker (`5x`). Усі об'єкти створюються в namespace `fleet-management`.

### Порядок розгортання

```powershell
# 1. Кластер з драйвером docker та доповнення
minikube start --driver=docker --cpus=4 --memory=6g
minikube addons enable metrics-server
minikube addons enable ingress

# 2. Образи з конкретними тегами версій (latest не використовується)
docker build -t fleet-management-api:1.0.0 --build-arg APP_VERSION=1.0.0 -f Dockerfile .
docker build -t fleet-management-api:1.1.0 --build-arg APP_VERSION=1.1.0 -f Dockerfile .
docker build -t fleet-management-worker:1.0.0 -f Dockerfile.worker .
minikube image load fleet-management-api:1.0.0
minikube image load fleet-management-api:1.1.0
minikube image load fleet-management-worker:1.0.0

# 3. Увесь застосунок однією командою
kubectl apply -f k8s/
kubectl rollout status deployment/api -n fleet-management
```

Доступ з хоста:

- **Ingress:** у терміналі адміністратора запустити `minikube tunnel`, додати рядок `127.0.0.1 fleet.local` у `C:\Windows\System32\drivers\etc\hosts` і відкрити http://fleet.local/docs.
- **NodePort (запасний варіант):** `minikube service api -n fleet-management --url`.

Службові ендпоінти API: `/livez` — liveness-проба (без залежностей), `/health` — readiness-проба (перевіряє БД), `/info` — назва застосунку, версія образу та ім'я пода.

### Параметри ConfigMap `fleet-config`

| Ключ | Призначення |
|---|---|
| `APP_ENV` | Оточення (`sandbox`); ім'я БД `POSTGRES_DB` має закінчуватися на `_sandbox` |
| `APP_NAME` | Назва застосунку (у `/info` та заголовку OpenAPI) |
| `REDIS_URL` | Підключення до кешу Redis |
| `TELEMETRY_QUEUE` | Черга RabbitMQ, яку обробляє worker |
| `RESILIENCE_ENABLED` | Таймаути та повтори запитів до Redis |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Час життя JWT-токена |
| `POSTGRES_DB`, `POSTGRES_USER` | Назва БД та користувач |

### Параметри Secret `fleet-secret`

Значення використовуються лише для лабораторної роботи й не пов'язані з жодною робочою системою.

| Ключ | Призначення |
|---|---|
| `POSTGRES_PASSWORD` | Пароль БД; з нього складається `DATABASE_URL` |
| `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS` | Облікові дані брокера; з них складається `RABBITMQ_URL` |
| `JWT_SECRET_KEY` | Ключ підпису access-токенів |

