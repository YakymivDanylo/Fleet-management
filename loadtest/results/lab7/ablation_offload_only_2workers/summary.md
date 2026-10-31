## Overall

| Endpoint | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| **all** | 10770 | 27.4 | 239.2 | 1.5 | 3572.7 | 1558.6 | 0.00 |

## Per endpoint

| Endpoint | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| GET /auth/me | 1795 | 4.6 | 143.6 | 2.0 | 2235.5 | 720.9 | 0.00 |
| GET /stations | 1795 | 4.6 | 138.0 | 1.8 | 2578.2 | 695.4 | 0.00 |
| GET /vehicles | 1795 | 4.6 | 143.6 | 2.1 | 2520.9 | 730.3 | 0.00 |
| GET /vehicles/{id} | 1795 | 4.6 | 128.1 | 1.8 | 2248.2 | 710.9 | 0.00 |
| GET /vehicles/{id}/state | 1795 | 4.6 | 26.3 | 1.5 | 504.2 | 107.7 | 0.00 |
| POST /auth/login | 1795 | 4.6 | 855.4 | 50.1 | 3572.7 | 2310.0 | 0.00 |

## Per load step (plateaus of >= 20 s)

| VUs | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| 10 | 457 | 7.4 | 14.9 | 1.6 | 122.7 | 74.1 | 0.00 |
| 25 | 1120 | 18.4 | 18.9 | 1.5 | 291.1 | 98.0 | 0.00 |
| 50 | 2162 | 36.0 | 57.4 | 1.6 | 924.9 | 324.7 | 0.00 |
| 100 | 3215 | 52.7 | 549.6 | 1.9 | 3572.7 | 2107.7 | 0.00 |

Duration: 393 s; peak RPS (5-s window): 60.6 at t=315 s (100 VUs)

## Server resources (docker stats, ~2 s samples)

| Container | CPU avg, % | CPU max, % | RAM avg, MiB | RAM max, MiB |
|---|---|---|---|---|
| api1 | 93.2 | 211.1 | 107 | 212 |
| api2 | 2.6 | 28.0 | 68 | 82 |
| api3 | 2.7 | 27.0 | 68 | 81 |
| db | 2.3 | 11.1 | 63 | 114 |
| k6-run | 2.9 | 7.1 | 36 | 47 |
| nginx | 1.4 | 5.6 | 9 | 14 |
| rabbitmq | 17.1 | 171.0 | 99 | 172 |
| redis | 0.9 | 3.6 | 4 | 9 |
| worker | 0.0 | 0.1 | 57 | 58 |
