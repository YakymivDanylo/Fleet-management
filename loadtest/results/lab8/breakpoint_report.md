## Final metrics (k6, load phase)

| Metric | Value |
|---|---|
| Requests (incl. setup) | 60059 |
| RPS (mean) | 82.1 |
| Latency avg, ms | 196.6 |
| Latency min, ms | -1.75 |
| Latency median, ms | 3.8 |
| Latency max, ms | 12250.5 |
| Latency p90, ms | 258.8 |
| Latency p95, ms | 1362.9 |
| Latency p99, ms | 4079.8 |
| Failed requests | 0 |
| Error rate, % | 0.0000 |
| Iterations (sessions) | 9993 |
| Peak VUs | 186 |

## Resource usage (Prometheus, 15-s samples)

| Metric | Mean | Max | Max vs limit | Trend |
|---|---|---|---|---|
| api1 RAM, MiB | 91 | 147 | 29 % of 512 | +347.4/h |
| api2 RAM, MiB | 103 | 143 | 28 % of 512 | +356.0/h |
| api3 RAM, MiB | 95 | 148 | 29 % of 512 | +358.1/h |
| api1 CPU, % of quota | 42 | 105 |  | +593.1/h |
| api2 CPU, % of quota | 69 | 103 |  | +292.0/h |
| api3 CPU, % of quota | 46 | 105 |  | +613.8/h |
| api1:8000 process RSS, MiB | 106 | 157 |  | +321.1/h |
| api2:8000 process RSS, MiB | 118 | 161 |  | +145.7/h |
| api3:8000 process RSS, MiB | 111 | 160 |  | +395.0/h |
| api1:8000 open FDs | 24 | 82 |  | +158.03/h |
| api2:8000 open FDs | 29 | 142 |  | +265.10/h |
| api3:8000 open FDs | 26 | 144 |  | +186.91/h |
| db RAM, MiB | 122 | 302 |  | +999.2/h |
| nginx RAM, MiB | 12 | 16 |  | +15.6/h |
| rabbitmq RAM, MiB | 138 | 207 |  | +28.2/h |
| redis RAM, MiB | 8 | 12 |  | -0.3/h |
| worker RAM, MiB | 57 | 57 |  | +0.0/h |
| db CPU, % of host | 0.4 | 2.0 |  | +4.77/h |
| nginx CPU, % of host | 0.4 | 1.1 |  | +3.57/h |
| rabbitmq CPU, % of host | 2.5 | 21.6 |  | -4.64/h |
| redis CPU, % of host | 0.2 | 0.5 |  | +0.86/h |
| worker CPU, % of host | 0.0 | 0.0 |  | -0.00/h |

## Latency drift: minutes 2-4 vs the last 2 minutes

| Metric | Start | End |
|---|---|---|
| avg, ms | 11 | 392 |
| p95, ms | 68 | 2243 |
| p99, ms | 75 | 3651 |
