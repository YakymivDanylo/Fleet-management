## Overall

| Endpoint | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| **all** | 10926 | 27.8 | 224.4 | 1.1 | 3394.9 | 1612.7 | 0.00 |

## Per endpoint

| Endpoint | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| GET /auth/me | 1821 | 4.6 | 174.5 | 1.9 | 1909.5 | 892.1 | 0.00 |
| GET /stations | 1821 | 4.6 | 35.5 | 1.1 | 1456.5 | 74.9 | 0.00 |
| GET /vehicles | 1821 | 4.6 | 32.1 | 1.1 | 1867.6 | 73.3 | 0.00 |
| GET /vehicles/{id} | 1821 | 4.6 | 161.9 | 1.8 | 1986.4 | 870.6 | 0.00 |
| GET /vehicles/{id}/state | 1821 | 4.6 | 26.0 | 1.4 | 1282.9 | 88.9 | 0.00 |
| POST /auth/login | 1821 | 4.6 | 916.4 | 50.2 | 3394.9 | 2457.0 | 0.00 |

## Per load step (plateaus of >= 20 s)

| VUs | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| 10 | 463 | 7.5 | 15.7 | 1.3 | 213.5 | 72.3 | 0.00 |
| 25 | 1132 | 18.6 | 19.1 | 1.2 | 393.2 | 95.3 | 0.00 |
| 50 | 2154 | 35.3 | 70.7 | 1.2 | 2361.2 | 355.6 | 0.00 |
| 100 | 3436 | 54.5 | 488.0 | 1.5 | 3394.9 | 2220.0 | 0.00 |

Duration: 393 s; peak RPS (5-s window): 59.2 at t=365 s (92 VUs)

## Server resources (docker stats, ~2 s samples)

| Container | CPU avg, % | CPU max, % | RAM avg, MiB | RAM max, MiB |
|---|---|---|---|---|
| api1 | 95.1 | 221.9 | 108 | 214 |
| api2 | 2.7 | 66.4 | 68 | 80 |
| api3 | 2.6 | 63.9 | 68 | 82 |
| db | 2.0 | 18.1 | 63 | 113 |
| k6-run | 3.1 | 9.5 | 37 | 46 |
| nginx | 1.5 | 9.2 | 9 | 14 |
| rabbitmq | 17.0 | 168.8 | 99 | 170 |
| redis | 1.1 | 8.1 | 5 | 9 |
| worker | 0.0 | 0.1 | 57 | 58 |
