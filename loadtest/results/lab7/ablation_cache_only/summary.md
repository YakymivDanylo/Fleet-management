## Overall

| Endpoint | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| **all** | 10032 | 25.5 | 359.4 | 1.2 | 6760.6 | 1724.7 | 0.00 |

## Per endpoint

| Endpoint | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| GET /auth/me | 1672 | 4.2 | 366.1 | 2.0 | 5836.8 | 1749.3 | 0.00 |
| GET /stations | 1672 | 4.2 | 322.1 | 1.2 | 6760.6 | 1593.1 | 0.00 |
| GET /vehicles | 1672 | 4.2 | 385.9 | 1.2 | 6237.0 | 1897.8 | 0.00 |
| GET /vehicles/{id} | 1672 | 4.2 | 317.9 | 1.8 | 6179.8 | 1531.2 | 0.00 |
| GET /vehicles/{id}/state | 1672 | 4.2 | 301.6 | 1.5 | 6608.3 | 1385.2 | 0.00 |
| POST /auth/login | 1672 | 4.2 | 463.0 | 49.3 | 6453.8 | 1908.8 | 0.00 |

## Per load step (plateaus of >= 20 s)

| VUs | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| 10 | 460 | 7.3 | 16.9 | 1.6 | 233.2 | 76.3 | 0.00 |
| 25 | 1120 | 18.4 | 21.0 | 1.2 | 225.7 | 95.3 | 0.00 |
| 50 | 2120 | 34.8 | 91.8 | 1.4 | 813.3 | 373.4 | 0.00 |
| 100 | 2686 | 42.6 | 987.5 | 1.3 | 6760.6 | 3241.5 | 0.00 |

Duration: 394 s; peak RPS (5-s window): 57.4 at t=300 s (100 VUs)

## Server resources (docker stats, ~2 s samples)

| Container | CPU avg, % | CPU max, % | RAM avg, MiB | RAM max, MiB |
|---|---|---|---|---|
| api1 | 87.9 | 211.8 | 89 | 149 |
| api2 | 2.8 | 70.7 | 68 | 82 |
| api3 | 2.1 | 59.9 | 68 | 82 |
| db | 1.8 | 18.7 | 52 | 70 |
| k6-run | 3.1 | 9.1 | 37 | 46 |
| nginx | 1.4 | 8.9 | 9 | 13 |
| rabbitmq | 19.2 | 198.8 | 99 | 167 |
| redis | 1.1 | 7.8 | 5 | 9 |
| worker | 0.0 | 0.1 | 57 | 58 |
