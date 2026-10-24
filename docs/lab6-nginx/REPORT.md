# Звіт: Лабораторна робота №6 — Балансування навантаження за допомогою Nginx

**Застосунок:** Fleet Management (каршерінг): FastAPI + PostgreSQL + Redis + RabbitMQ
**Гілка:** `feat/lab6-nginx-lb`
**Дата виконання:** 2026-10-24

Сирі виводи команд лежать у [`outputs/`](outputs/), результати k6 — у [`loadtest/results/lab6/`](../../loadtest/results/lab6/).

## 1. Що зроблено

| Завдання | Реалізація |
|---|---|
| 1. Кілька реплік | У [`docker-compose.yml`](../../docker-compose.yml) три однакові сервіси `api1`, `api2`, `api3` (спільний YAML-якір). Кожна репліка має власний `hostname`, а `GET /info` повертає його в полі `pod`. Це унікальна ідентифікація сервера, окремої зміни коду не потрібно. |
| 2. Nginx як Load Balancer | Сервіс `nginx` (образ `nginx:1.27-alpine`) + конфіги у [`nginx/`](../../nginx/): блок `upstream fleet_api` з усіма трьома репліками, `server { listen 80; location / { proxy_pass http://fleet_api; } }`. Порт `${API_PORT:-8000}` хоста тепер веде на Nginx, тож усі старі URL (`localhost:8000`) працюють. |
| 3. Round Robin | Алгоритм за замовчуванням, [`nginx/round_robin.conf`](../../nginx/round_robin.conf). Перевірка — розділ 3. |
| 4. Health checks / відмовостійкість | Пасивні перевірки: `max_fails=2 fail_timeout=10s` + `proxy_next_upstream`. Перевірка — розділ 4. |
| Дод. 1. Інші алгоритми | `weight` (3:2:1), `ip_hash`, `least_conn` — розділ 5. |
| Дод. 2. Порівняння RPS/Latency | k6 (інструмент ЛР4): 1 репліка проти 3 — розділ 6. |

### Архітектура

```
 клієнт ──► localhost:8000 ──► nginx:80 ──┬──► api1:8000 ─┐
                                          ├──► api2:8000 ─┼──► db / redis (мережа backend)
                                          └──► api3:8000 ─┘
```

Репліки не публікують портів і сидять лише в `internal`-мережі `backend`: достукатися до них можна тільки через Nginx.

### Проблеми, які виявлені й виправлені

1. **Гонка міграцій.** Образ запускає `alembic upgrade head` у `CMD`. Три репліки одночасно мігрували б одну БД. Міграції винесено в одноразовий сервіс `migrate`, а репліки стартують після `service_completed_successfully` і запускають лише `uvicorn`. Kubernetes-маніфести та `Dockerfile` не змінювались.
2. **Порт 8000 не можна опублікувати з трьох реплік**, тому його публікує тільки Nginx.
3. **Нестрога ротація Round Robin.** Кожен worker-процес Nginx мав власний лічильник, і перші запити могли йти поспіль на одну репліку (8 запитів на `api1` підряд). Виправлення: `zone fleet_api 64k;` в `upstream` — стан балансування (позиція ротації, лічильники збоїв) переходить у спільну пам'ять.
4. **IP клієнта в аудиті.** `auth.py` пише `request.client.host`; за проксі це була б адреса Nginx. `uvicorn` запускається з `--proxy-headers --forwarded-allow-ips=*` (безпечно, бо репліки доступні лише з внутрішньої мережі), а Nginx передає `X-Forwarded-For`.
5. **Інші залежності від імені `api`:** `worker` тепер чекає `api1`, `k6` ходить на `http://nginx`, hot-reload у `docker-compose.dev.yml` застосовано до `api1`, у README команду `exec api` замінено на `exec api1`.
6. **Нюанс health check.** Open-source Nginx не має активних перевірок (це функція Nginx Plus), тому використано пасивні: збій виявляється на реальному запиті й тут же повторюється на іншій репліці, тож клієнт помилки не бачить. Ціна — перші запити після падіння репліки коштують +1 с (`proxy_connect_timeout 1s`).

## 2. Інструкція запуску (спільна для всіх демонстрацій)

Потрібні Docker Desktop і заповнений `.env` (див. `.env.example`, блок «one-command start»).

```powershell
docker compose up -d --build
docker compose ps                      # api1/api2/api3/nginx мають бути (healthy)
```

Результат: [`outputs/01-compose-ps.txt`](outputs/01-compose-ps.txt) — три репліки, `nginx` слухає `0.0.0.0:8000->80`. Налаштований upstream: [`outputs/01b-upstream.txt`](outputs/01b-upstream.txt) (або `docker compose exec nginx nginx -T`).

Для демонстрацій потрібен Python 3 (скрипт використовує тільки стандартну бібліотеку).

## 3. Демонстрація: Round Robin (завдання 3)

```powershell
python scripts/lb_check.py -n 15
```

Скрипт робить 15 послідовних запитів на `GET /info`. Колонка `replica` — це `pod` з відповіді, `upstream` — заголовок `X-Upstream-Addr`, який додає Nginx.

```
  #  HTTP  replica  upstream           time
  1   200  api1     172.20.0.5:8000    63 ms
  2   200  api2     172.20.0.6:8000    15 ms
  3   200  api3     172.20.0.7:8000    3 ms
  4   200  api1     ...
  ...
Requests per replica:  api1 5   api2 5   api3 5
Failed requests: 0 of 15
```

Повний вивід: [`outputs/02-round-robin.txt`](outputs/02-round-robin.txt). Репліки опитуються строго по колу api1 → api2 → api3. Те саме видно в логах Nginx: `docker compose logs nginx` (поле `upstream=`).

Можна й вручну: `curl -i http://localhost:8000/info` кілька разів — змінюється `"pod"` і заголовок `X-Upstream-Addr`.

## 4. Демонстрація: відмовостійкість (завдання 4)

Відкрийте два термінали.

**Термінал A** — безперервний потік запитів із паузою 0.4 с (у збереженому виводі їх 16, тут беремо з запасом):

```powershell
python scripts/lb_check.py -n 40 --delay 0.4
```

**Термінал B** — під час потоку зупиніть одну репліку:

```powershell
docker stop fleet_lab5-api2-1          # ім'я = <COMPOSE_PROJECT_NAME>-api2-1, див. docker compose ps
docker compose ps                      # api2 зник зі списку
docker compose logs nginx --tail 20    # [error] ... upstream timed out ... та [warn] ... temporarily disabled
```

Що спостерігаємо ([`outputs/03-failover-requests.txt`](outputs/03-failover-requests.txt)):

- `Failed requests: 0 of 16` — **жоден запит не втрачено**;
- відповіді йдуть лише від `api1` і `api3`, у стовпці `upstream` двічі з'являється пара `172.20.0.6:8000, 172.20.0.7:8000` з часом ≈1 с — Nginx спробував мертву `api2`, за 1 с (`proxy_connect_timeout`) відмовився і повторив запит на `api3`;
- після двох збоїв поспіль (`max_fails=2`) Nginx пише `upstream server temporarily disabled` і **наступні 10 с (`fail_timeout`) взагалі не звертається до `api2`** — запити знову швидкі (3–30 мс), весь трафік ділять `api1` і `api3` ([`outputs/03b-failover-nginx-log.txt`](outputs/03b-failover-nginx-log.txt)).

Відновлення:

```powershell
docker start fleet_lab5-api2-1
# за ~20 с контейнер стає healthy, а після закінчення fail_timeout Nginx сам повертає його в ротацію
python scripts/lb_check.py -n 12
```

Результат: [`outputs/03d-recovery.txt`](outputs/03d-recovery.txt) — знову по 4 запити на кожну репліку, без перезапуску Nginx.

## 5. Додаткове завдання 1: інші алгоритми

Алгоритм змінюється підстановкою іншого конфігу (змінну `NGINX_CONF` можна записати в `.env` або задати в терміналі):

```powershell
$env:NGINX_CONF = "./nginx/weighted.conf"      # weighted.conf | ip_hash.conf | least_conn.conf | round_robin.conf
docker compose up -d --force-recreate nginx
python scripts/lb_check.py -n 12
Remove-Item Env:NGINX_CONF                     # повернення до Round Robin
```

| Алгоритм | Директива | 12 запитів: api1 / api2 / api3 | Висновок |
|---|---|---|---|
| Weighted RR | `weight=3`, `weight=2`, `weight=1` | **6 / 4 / 2** ([вивід](outputs/04-weighted.txt)) | точно відповідає вагам 3:2:1; підходить, якщо репліки різної потужності |
| IP Hash | `ip_hash;` | **12 / 0 / 0** ([вивід](outputs/05-ip-hash.txt)) | один клієнт (одна IP) прив'язаний до однієї репліки — «липкі» сесії |
| Least Connections | `least_conn;` | 4 / 4 / 4 ([вивід](outputs/06-least-conn-sequential.txt)) | при послідовних запитах активних з'єднань завжди 0, тож поведінка збігається з RR; перевагу показує лише паралельне навантаження з нерівномірними за тривалістю запитами |

Примітка: у цьому застосунку сесії stateless (JWT), тому `ip_hash` не потрібен для коректності. Крім того, за Docker Desktop усі запити з хоста мають одну адресу шлюзу, тож `ip_hash` тут завжди обирає одну репліку.

## 6. Додаткове завдання 2: 1 репліка проти 3 реплік

**Методика.** Той самий Nginx, той самий сценарій [`loadtest/user_journey.js`](../../loadtest/user_journey.js) (інструмент із ЛР4), новий профіль `compare`: 60 VUs, 60 с, `THINK=0` (без пауз, щоб міряти пропускну здатність, а не «час читання»). Єдина відмінність — конфіг: [`nginx/single.conf`](../../nginx/single.conf) (upstream лише з `api1`) проти [`nginx/round_robin.conf`](../../nginx/round_robin.conf) (`api1..api3`). Кожна репліка має однакову квоту 2 CPU / 512 МБ. Кожна конфігурація запускалась двічі (прогрів не враховано).

```powershell
python scripts/seed_loadtest.py --vehicles 50          # один раз
$env:NGINX_CONF = "./nginx/single.conf"; docker compose up -d --force-recreate nginx
docker compose run --rm --no-deps -e PROFILE=compare -e THINK=0 -e VUS=60 k6 run /scripts/user_journey.js
$env:NGINX_CONF = "./nginx/round_robin.conf"; docker compose up -d --force-recreate nginx
docker compose run --rm --no-deps -e PROFILE=compare -e THINK=0 -e VUS=60 k6 run /scripts/user_journey.js
```

**Результати** (тільки фаза навантаження, `phase:load`; 8 vCPU / 12 ГБ, Docker Desktop, Windows 11):

| Показник | 1 репліка (2 запуски) | 3 репліки (2 запуски) | Зміна |
|---|---|---|---|
| Запитів за 60 с | 3954 / 3948 | 7662 / 7476 | ×1.9 |
| **RPS** (запити / 60 с) | **≈ 66** | **≈ 126** | **×1.9** |
| Latency, середня | 977 / 975 мс | 475 / 487 мс | −51 % |
| Latency, p95 | 4490 / 4379 мс | 1132 / 1073 мс | −75 % |
| Latency, p99 | 5022 / 4867 мс | 1383 / 1783 мс | −71 % |
| `POST /auth/login`, p95 | 4911 / 4816 мс | 1256 / 1306 мс | −74 % |
| Помилки (`http_req_failed`) | 0 % | 0 % | — |

Сирі дані: [`single_1`, `single_2`, `three_1`, `three_2`](../../loadtest/results/lab6/) (`.json` — експорт підсумку k6, `.txt` — консольний вивід).

**Висновки.**

- Три репліки дають приблизно вдвічі більшу пропускну здатність (×1.9, а не ×3) і в 3–4 рази менший хвіст затримки p95. Вузьке місце — CPU реплік, насамперед хешування Argon2id у `POST /auth/login` (при одній репліці p95 логіна ≈ 4.9 с, при трьох ≈ 1.3 с).
- Масштабування не лінійне: Postgres, Redis, Nginx і сам k6 ділять ті самі 8 vCPU хоста, а БД — спільна для всіх реплік.
- Для порівняння із SLO ЛР4 (`p95 < 500 мс`) 60 VUs без пауз — це навмисне перевантаження: поріг порушують обидві конфігурації, але з трьома репліками p95 у 4 рази ближчий до цілі.
- Результати відтворюються: розбіжність між двома запусками однієї конфігурації — у межах 2–3 % за RPS.

> Методична примітка. Перший наш прогін дав некоректні цифри, бо одночасно працювали дві копії тестового скрипта (у `docker stats` було видно 189 % CPU на `api1` при простоюючому тесті). Такі прогони відкинуто й повторено на «чистому» стенді, тому для порівняння важливо перевіряти, що жодного зайвого k6-контейнера не залишилось (`docker ps -a | findstr k6`).

## 7. Зміни у файлах

| Файл | Зміна |
|---|---|
| `docker-compose.yml` | сервіси `migrate`, `api1..3`, `nginx`; прибрано `api`; `worker`/`k6` залежать від нових сервісів |
| `docker-compose.dev.yml` | hot-reload для `api1`, міграції не запускаються в команді |
| `nginx/*.conf` | `round_robin`, `weighted`, `ip_hash`, `least_conn`, `single` |
| `loadtest/user_journey.js` | профіль `compare`, змінні `THINK`, `VUS`, `DURATION` |
| `scripts/lb_check.py` | утиліта для демонстрації розподілу запитів |
| `README.md` | розділ про балансування, `exec api1` |
| `docs/lab6-nginx/` | цей звіт і виводи команд |

## 8. Прибирання

```powershell
docker compose down            # додайте -v, щоб видалити дані БД
```
