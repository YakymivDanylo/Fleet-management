## Overall

| Endpoint | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| **all** | 11658 | 29.8 | 119.1 | 1.2 | 2114.3 | 511.2 | 0.00 |

## Per endpoint

| Endpoint | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| GET /auth/me | 1943 | 5.0 | 87.9 | 1.6 | 1339.1 | 392.1 | 0.00 |
| GET /stations | 1943 | 5.0 | 92.5 | 1.2 | 1864.2 | 420.2 | 0.00 |
| GET /vehicles | 1943 | 5.0 | 106.2 | 1.7 | 1476.0 | 513.3 | 0.00 |
| GET /vehicles/{id} | 1943 | 5.0 | 113.4 | 1.4 | 2114.3 | 555.4 | 0.00 |
| GET /vehicles/{id}/state | 1943 | 5.0 | 107.0 | 1.4 | 1432.0 | 463.3 | 0.00 |
| POST /auth/login | 1943 | 5.0 | 207.7 | 54.1 | 1393.7 | 677.6 | 0.00 |

## Per load step (plateaus of >= 20 s)

| VUs | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| 10 | 446 | 7.2 | 17.9 | 1.5 | 149.9 | 85.7 | 0.00 |
| 25 | 1151 | 18.6 | 20.6 | 1.4 | 206.6 | 90.7 | 0.00 |
| 50 | 2163 | 36.0 | 39.7 | 1.2 | 632.9 | 160.4 | 0.00 |
| 100 | 3992 | 63.4 | 228.2 | 1.3 | 2114.3 | 699.3 | 0.00 |

Duration: 391 s; peak RPS (5-s window): 69.0 at t=350 s (100 VUs)

## Server resources (docker stats, ~2 s samples)

| Container | CPU avg, % | CPU max, % | RAM avg, MiB | RAM max, MiB |
|---|---|---|---|---|
| api | 100.8 | 323.5 | 88 | 140 |
| db | 4.0 | 21.7 | 56 | 109 |
| k6-run | 3.0 | 9.6 | 38 | 48 |
| rabbitmq | 16.9 | 187.8 | 99 | 169 |
| redis | 0.9 | 3.5 | 4 | 7 |
| worker | 0.0 | 0.1 | 57 | 57 |
