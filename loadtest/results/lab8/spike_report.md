## Final metrics (k6, load phase)

| Metric | Value |
|---|---|
| Requests (incl. setup) | 49757 |
| RPS (mean) | 100.0 |
| Latency avg, ms | 2935.5 |
| Latency min, ms | 0.06 |
| Latency median, ms | 2.8 |
| Latency max, ms | 60000.4 |
| Latency p90, ms | 14759.6 |
| Latency p95, ms | 25501.9 |
| Latency p99, ms | 30000.0 |
| Failed requests | 11491 |
| Error rate, % | 23.1412 |
| Iterations (sessions) | 10576 |
| Peak VUs | 1500 |

## Resource usage (Prometheus, 15-s samples)

| Metric | Mean | Max | Max vs limit | Trend |
|---|---|---|---|---|
| api1 RAM, MiB | 128 | 187 | 36 % of 512 | +204.4/h |
| api2 RAM, MiB | 143 | 206 | 40 % of 512 | +391.3/h |
| api3 RAM, MiB | 134 | 189 | 37 % of 512 | +144.3/h |
| api1 CPU, % of quota | 64 | 103 |  | -147.8/h |
| api2 CPU, % of quota | 54 | 103 |  | -127.1/h |
| api3 CPU, % of quota | 67 | 104 |  | -95.5/h |
| api1:8000 process RSS, MiB | 130 | 189 |  | +147.6/h |
| api2:8000 process RSS, MiB | 141 | 206 |  | +506.9/h |
| api3:8000 process RSS, MiB | 136 | 195 |  | +165.2/h |
| api1:8000 open FDs | 106 | 492 |  | -726.74/h |
| api2:8000 open FDs | 142 | 878 |  | -630.64/h |
| api3:8000 open FDs | 124 | 650 |  | -635.21/h |
| db RAM, MiB | 188 | 309 |  | -339.7/h |
| nginx RAM, MiB | 20 | 39 |  | +8.3/h |
| rabbitmq RAM, MiB | 138 | 201 |  | +68.8/h |
| redis RAM, MiB | 9 | 9 |  | +1.5/h |
| worker RAM, MiB | 57 | 57 |  | +0.0/h |
| db CPU, % of host | 0.4 | 1.4 |  | +0.17/h |
| nginx CPU, % of host | 0.5 | 0.9 |  | +0.31/h |
| rabbitmq CPU, % of host | 2.1 | 22.6 |  | +16.33/h |
| redis CPU, % of host | 0.2 | 0.5 |  | -0.40/h |
| worker CPU, % of host | 0.0 | 0.0 |  | +0.00/h |

## Latency drift: minutes 2-3 vs the last 1 minutes

| Metric | Start | End |
|---|---|---|
| avg, ms | 4067 | 17 |
| p95, ms | 6823 | 92 |
| p99, ms | 7503 | 218 |
