## Overall

| Endpoint | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| **all** | 11556 | 29.5 | 143.8 | 1.1 | 2162.1 | 1310.8 | 0.00 |

## Per endpoint

| Endpoint | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| GET /auth/me | 1926 | 4.9 | 74.6 | 2.1 | 1095.7 | 439.2 | 0.00 |
| GET /stations | 1926 | 4.9 | 8.5 | 1.1 | 143.2 | 39.9 | 0.00 |
| GET /vehicles | 1926 | 4.9 | 9.3 | 1.1 | 269.4 | 40.4 | 0.00 |
| GET /vehicles/{id} | 1926 | 4.9 | 70.7 | 1.8 | 887.4 | 416.6 | 0.00 |
| GET /vehicles/{id}/state | 1926 | 4.9 | 8.3 | 1.4 | 117.0 | 50.2 | 0.00 |
| POST /auth/login | 1926 | 4.9 | 691.5 | 50.6 | 2162.1 | 1857.9 | 0.00 |

## Per load step (plateaus of >= 20 s)

| VUs | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| 10 | 468 | 7.5 | 14.4 | 1.4 | 158.7 | 70.9 | 0.00 |
| 25 | 1150 | 18.3 | 17.9 | 1.1 | 499.2 | 81.3 | 0.00 |
| 50 | 2307 | 37.2 | 25.3 | 1.1 | 519.1 | 144.2 | 0.00 |
| 100 | 3806 | 60.4 | 336.0 | 1.4 | 2162.1 | 1713.5 | 0.00 |

Duration: 392 s; peak RPS (5-s window): 64.2 at t=345 s (100 VUs)

## Server resources (docker stats, ~2 s samples)

| Container | CPU avg, % | CPU max, % | RAM avg, MiB | RAM max, MiB |
|---|---|---|---|---|
| api1 | 90.6 | 205.4 | 92 | 148 |
| api2 | 2.5 | 27.0 | 68 | 81 |
| api3 | 2.5 | 26.7 | 68 | 82 |
| db | 1.8 | 9.9 | 62 | 115 |
| k6-run | 3.1 | 7.8 | 37 | 46 |
| nginx | 1.5 | 4.9 | 9 | 14 |
| rabbitmq | 16.3 | 173.2 | 98 | 173 |
| redis | 1.0 | 4.0 | 5 | 9 |
| worker | 0.0 | 0.1 | 57 | 57 |
