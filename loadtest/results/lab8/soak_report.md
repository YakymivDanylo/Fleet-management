## Final metrics (k6, load phase)

| Metric | Value |
|---|---|
| Requests (incl. setup) | 302507 |
| RPS (mean) | 83.9 |
| Latency avg, ms | 15.1 |
| Latency min, ms | 0.12 |
| Latency median, ms | 2.6 |
| Latency max, ms | 648.9 |
| Latency p90, ms | 58.7 |
| Latency p95, ms | 75.7 |
| Latency p99, ms | 142.7 |
| Failed requests | 0 |
| Error rate, % | 0.0000 |
| Iterations (sessions) | 50401 |
| Peak VUs | 50 |

## Resource usage (Prometheus, 15-s samples)

| Metric | Mean | Max | Max vs limit | Trend |
|---|---|---|---|---|
| api1 RAM, MiB | 95 | 150 | 29 % of 512 | -9.4/h |
| api2 RAM, MiB | 96 | 154 | 30 % of 512 | +8.9/h |
| api3 RAM, MiB | 88 | 156 | 31 % of 512 | +2.9/h |
| api1 CPU, % of quota | 63 | 94 |  | +0.9/h |
| api2 CPU, % of quota | 50 | 103 |  | -1.7/h |
| api3 CPU, % of quota | 24 | 76 |  | -2.8/h |
| api1:8000 process RSS, MiB | 112 | 157 |  | +5.6/h |
| api2:8000 process RSS, MiB | 106 | 161 |  | -3.2/h |
| api3:8000 process RSS, MiB | 100 | 161 |  | +2.0/h |
| api1:8000 open FDs | 24 | 26 |  | -0.07/h |
| api2:8000 open FDs | 24 | 26 |  | -0.24/h |
| api3:8000 open FDs | 24 | 26 |  | -0.09/h |
| db RAM, MiB | 139 | 142 |  | +6.0/h |
| nginx RAM, MiB | 12 | 16 |  | -0.0/h |
| rabbitmq RAM, MiB | 136 | 208 |  | +6.0/h |
| redis RAM, MiB | 9 | 13 |  | +1.2/h |
| worker RAM, MiB | 57 | 57 |  | +0.0/h |
| db CPU, % of host | 0.4 | 1.4 |  | -0.04/h |
| nginx CPU, % of host | 0.4 | 0.8 |  | +0.00/h |
| rabbitmq CPU, % of host | 2.1 | 25.0 |  | +3.08/h |
| redis CPU, % of host | 0.2 | 0.5 |  | -0.00/h |
| worker CPU, % of host | 0.0 | 0.0 |  | +0.00/h |

## Latency drift: minutes 2-12 vs the last 10 minutes

| Metric | Start | End |
|---|---|---|
| avg, ms | 15 | 14 |
| p95, ms | 75 | 75 |
| p99, ms | 187 | 178 |
