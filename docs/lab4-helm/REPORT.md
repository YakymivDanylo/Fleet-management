# Звіт: Лабораторна робота №4 — Пакування застосунку в Helm-чарт

**Застосунок:** Fleet Management (каршерінг) — FastAPI API + telemetry worker, PostgreSQL, Redis, RabbitMQ
**Гілка:** `feat/lab4-helm`
**Чарт:** [`chart/fleet-management`](../../chart/fleet-management/README.md) (version `0.1.0`, appVersion `1.0.0`)
**Дата виконання:** 2026-10-13

Усі команди виконано на реальному кластері; повний вивід кожного кроку — у каталозі [`outputs/`](outputs/).

## Середовище (пункт 1)

| Компонент | Версія |
|---|---|
| Helm | v3.18.6 (`winget` ставить Helm 4, тому Helm 3 завантажено напряму з get.helm.sh) |
| minikube | драйвер `docker`, 4 CPU / 6 GiB, надбудови `ingress`, `metrics-server` |
| Kubernetes (сервер) | v1.37.0 |

| Крок | Підтвердження |
|---|---|
| 1a. Версія Helm | [`01-env.txt`](outputs/01-env.txt) |
| 1b. Кластер minikube запущено | [`01-env.txt`](outputs/01-env.txt) |
| 1c. Маніфести ЛР3 розгорнуті, застосунок відповідає (`/health` → `{"status":"ok","db":"connected"}`) | [`02-lab3-check.txt`](outputs/02-lab3-check.txt) |
| 1d. Реліз ЛР3 видалено (`kubectl delete -f k8s/`, namespace знищено) | [`03-lab3-cleanup.txt`](outputs/03-lab3-cleanup.txt) |

## Структура чарта (пункти 2–5)

- `Chart.yaml`: `name`, `description`, `version: 0.1.0`, `appVersion: "1.0.0"`; різниця між ними пояснена в [README чарта](../../chart/fleet-management/README.md#version-та-appversion).
- Кожен маніфест ЛР3 став окремим файлом у `templates/` (14 файлів + хук + тест). Namespace окремим шаблоном не є: його створює `helm install --create-namespace`.
- Імена всіх об'єктів будуються як `<реліз>-<чарт>-<компонент>` (`fleet-fleet-management-api` тощо) через `_helpers.tpl`; адреси сервісів у `DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL` та init-контейнері теж складаються з імені релізу. Тому чарт можна встановити двічі (перевірка — [`06-render-vs-lab3.txt`](outputs/06-render-vs-lab3.txt): імена двох релізів `fleet-a` / `fleet-b` не перетинаються). `service.nodePort` за замовчуванням `null`, щоб два релізи не конфліктували за порт 30080.
- `values.yaml` містить образи й теги, репліки, тип/порт сервісу, ресурси, `config.*`, `secret.*`, прапорці `ingress.enabled`, `postgres.persistence.enabled`, `rabbitmq.persistence.enabled` (вимкнено → `emptyDir`). Значення за замовчуванням відповідають dev. Додано `values.schema.json` (перевірка типів при `lint`/`install`).
- `_helpers.tpl`: іменовані шаблони `fleet.fullname`, `fleet.componentName`, `fleet.labels`, `fleet.selectorLabels`, `fleet.image`, `fleet.secretValue`; підключені в усіх маніфестах через `include`. `NOTES.txt` виводить інструкцію доступу залежно від `ingress.enabled` / `service.type`.
- **Secret:** шаблон бере значення з `.Values.secret.*`. Файли значень паролів не містять; порожнє значення означає «взяти з наявного Secret у кластері (`lookup`) або згенерувати `randAlphaNum 24`». Завдяки цьому паролі стабільні між `upgrade`/`rollback` (відбиток Secret до й після оновлень однаковий — [`10-upgrade-set-tag.txt`](outputs/10-upgrade-set-tag.txt)).

## Пункт 6. Два середовища

| Параметр | `values-dev.yaml` | `values-prod.yaml` |
|---|---|---|
| `replicaCount` | 1 | 3 |
| `image.tag` | 1.0.0 | 1.1.0 |
| `resources` (requests → limits) | 50m/96Mi → 250m/192Mi | 200m/192Mi → 750m/384Mi |
| `ingress.enabled` | false | true (`fleet.local`) |
| `config.appName` | Fleet Management (dev) | Fleet Management (prod) |

- **6b.** Різницю показано без встановлення: `diff` файлів значень і `diff` двох `helm template` — [`05-env-diff.txt`](outputs/05-env-diff.txt). У згенерованих маніфестах відрізняються лише `APP_NAME`, `replicas`, тег образу, ресурси та додатковий Ingress.
- **6c. Пріоритет значень:** `values.yaml` чарта → файли `-f` (кожен наступний перекриває попередній) → `--set` (найвищий). Підтверджено на рендері ([`05b-values-priority.txt`](outputs/05b-values-priority.txt)):

| Команда | replicas | image |
|---|---|---|
| лише `values.yaml` | 2 | 1.0.0 |
| `-f values-prod.yaml` | 3 | 1.1.0 |
| `-f values-prod.yaml --set replicaCount=5,image.tag=1.0.0` | 5 | 1.0.0 |
| `-f values-prod.yaml -f values-dev.yaml` | 1 | 1.0.0 |

## Пункт 7. Перевірка та встановлення

- **7a.** `helm lint` без помилок; негативна перевірка — `--set service.type=Bad` відхиляється схемою (`exit=1`): [`04-lint.txt`](outputs/04-lint.txt).
- **7b.** Порівняння з ЛР3 — [`06-render-vs-lab3.txt`](outputs/06-render-vs-lab3.txt). Набір об'єктів той самий (1 ConfigMap, 1 Secret, 2 PVC, 5 Deployment, 4 Service, Ingress за прапорцем). Відмінності: немає Namespace (його створює Helm), додано Job-хук, змінилися імена й мітки (додано `instance`/`component` у селектори, щоб релізи не перетиналися).
- **7c–d.** `helm install fleet chart/fleet-management -n fleet-management --create-namespace --wait` — однією командою на чистому namespace; `helm list`, `helm status`, `helm get values` — [`07-install.txt`](outputs/07-install.txt).
- **7e. Де Helm зберігає стан:** у Secret типу `helm.sh/release.v1` з іменем `sh.helm.release.v1.<реліз>.v<ревізія>` у namespace релізу (по одному на ревізію). Дані — gzip + base64 JSON з чартом, значеннями, маніфестом і статусом. Розшифровано в [`08-release-storage.txt`](outputs/08-release-storage.txt).

## Пункт 8. Життєвий цикл релізу

| Ревізія | Команда | Що змінилося | Підтвердження |
|---|---|---|---|
| 1 | `helm install fleet …` | Початкове встановлення: dev-значення, 2 репліки API, образ 1.0.0 | [`07-install.txt`](outputs/07-install.txt) |
| 2 | `helm upgrade fleet … --set image.tag=1.1.0` | Лише тег образу API 1.0.0 → 1.1.0 (`/info` повертає `"version":"1.1.0"`); перед оновленням відпрацював `pre-upgrade` хук | [`10-upgrade-set-tag.txt`](outputs/10-upgrade-set-tag.txt) |
| 3 | `helm upgrade fleet … -f values-prod.yaml` | 3 репліки, ресурси prod, `APP_NAME` prod, створено Ingress | [`11-upgrade-prod.txt`](outputs/11-upgrade-prod.txt) |
| 4 | `helm rollback fleet 2` | Повернення до стану ревізії 2 (2 репліки, образ 1.1.0, без Ingress); це **нова** ревізія з описом `Rollback to 2` | [`13-rollback.txt`](outputs/13-rollback.txt) |

Історія (`helm history`), значення кожної ревізії та `diff` маніфестів між ревізіями — [`12-history.txt`](outputs/12-history.txt). Відкат не «перемотує» історію назад, а додає ревізію 4; ревізії 1–3 лишаються `superseded`.

- **8e.** `helm uninstall fleet -n fleet-management` видаляє всі об'єкти релізу, включно з PVC та Secret зі станом Helm; у namespace лишається тільки службовий `kube-root-ca.crt`. Сам namespace Helm не видаляє (його створювали ми) — [`14-uninstall.txt`](outputs/14-uninstall.txt). Два `Released` PV в `kubectl get pv` — це залишки ЛР3 (`rabbitmq-data`, `postgres-data` віком 7 діб), не пов'язані з чартом.

## Пункт 9. Завдання на вибір: (b) хук і тест релізу

- **Хук** [`templates/hooks/pre-upgrade-job.yaml`](../../chart/fleet-management/templates/hooks/pre-upgrade-job.yaml): Job із анотацією `helm.sh/hook: pre-upgrade` виконує `pg_isready` до PostgreSQL перед кожним `helm upgrade`; політика `before-hook-creation,hook-succeeded`. Якщо БД недоступна, Job падає й оновлення не починається. Відпрацювання підтверджують події `SuccessfulCreate` → `Completed` у [`10-upgrade-set-tag.txt`](outputs/10-upgrade-set-tag.txt). Вимикається `hooks.preUpgrade.enabled=false`.
- **Тест** [`templates/tests/test-api.yaml`](../../chart/fleet-management/templates/tests/test-api.yaml): Pod з анотацією `helm.sh/hook: test` запитує `/health` і `/info` через Service релізу та завершується з кодом 1, якщо `status != ok` або БД не підключена. `helm test fleet` → `Phase: Succeeded`: [`09-helm-test.txt`](outputs/09-helm-test.txt); повторно після переходу на prod — [`11-upgrade-prod.txt`](outputs/11-upgrade-prod.txt).

## Відповідність вимогам до здачі

| Вимога | Статус |
|---|---|
| Той самий застосунок і набір об'єктів, що в ЛР3 | Так (пункт 7b) |
| Немає жорстко прописаних імені релізу, тега образу, кількості реплік | Так: імена через `include`, теги й репліки з `.Values`; єдині збіги пошуку в `templates/` — імена контейнерів усередині подів ([`06-render-vs-lab3.txt`](outputs/06-render-vs-lab3.txt)) |
| Встановлення на чистому кластері однією командою | Так (пункт 7c) |
| Реальні паролі у файлах значень не зберігаються | Так: `secret.*` порожні, значення генеруються або передаються через `--set` |

## Обмеження та спостереження

- Образи `fleet-management-*` збираються локально й завантажуються в minikube (`minikube image load`), як і в ЛР3; у реєстр вони не публікуються.
- Згенеровані паролі існують лише в Secret кластера. Після `helm uninstall` разом з PVC зникають і дані БД, тож при новому встановленні пароль і база створюються заново узгоджено.
- `lookup` не працює під час `helm template` та `--dry-run` (там паролі завжди випадкові) — на реальний `install`/`upgrade` це не впливає.
