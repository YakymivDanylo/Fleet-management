## Overall

| Endpoint | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| **all** | 11082 | 28.1 | 206.3 | 1.3 | 1511.0 | 821.3 | 0.00 |

## Per endpoint

| Endpoint | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| GET /auth/me | 1847 | 4.7 | 211.1 | 1.9 | 1493.1 | 811.5 | 0.00 |
| GET /stations | 1847 | 4.7 | 167.4 | 1.6 | 1320.4 | 712.9 | 0.00 |
| GET /vehicles | 1847 | 4.7 | 187.7 | 2.0 | 1398.9 | 814.9 | 0.00 |
| GET /vehicles/{id} | 1847 | 4.7 | 187.9 | 1.3 | 1474.9 | 817.4 | 0.00 |
| GET /vehicles/{id}/state | 1847 | 4.7 | 192.7 | 1.5 | 1503.7 | 828.6 | 0.00 |
| POST /auth/login | 1847 | 4.7 | 290.7 | 49.2 | 1511.0 | 891.8 | 0.00 |

## Per load step (plateaus of >= 20 s)

| VUs | Requests | RPS | Avg, ms | Min, ms | Max, ms | p95, ms | Errors, % |
|---|---|---|---|---|---|---|---|
| 10 | 470 | 7.5 | 20.4 | 1.7 | 446.2 | 99.5 | 0.00 |
| 25 | 1086 | 17.8 | 74.5 | 1.8 | 1047.8 | 400.9 | 0.00 |
| 50 | 2156 | 35.9 | 57.5 | 1.3 | 490.3 | 221.5 | 0.00 |
| 100 | 3618 | 56.5 | 434.8 | 1.6 | 1511.0 | 1062.4 | 0.00 |

Duration: 394 s; peak RPS (5-s window): 64.2 at t=295 s (100 VUs)

## Server resources (docker stats, ~2 s samples)

| Container | CPU avg, % | CPU max, % | RAM avg, MiB | RAM max, MiB |
|---|---|---|---|---|
| api1 | 88.6 | 203.2 | 89 | 149 |
| api2 | 2.7 | 68.3 | 68 | 81 |
| api3 | 2.8 | 68.7 | 68 | 81 |
| db | 2.2 | 14.9 | 54 | 76 |
| k6-run | 3.0 | 7.6 | 38 | 47 |
| nginx | 1.4 | 6.7 | 9 | 14 |
| rabbitmq | 19.2 | 224.9 | 100 | 171 |
| redis | 0.9 | 6.9 | 4 | 8 |
| worker | 0.0 | 0.1 | 57 | 58 |
