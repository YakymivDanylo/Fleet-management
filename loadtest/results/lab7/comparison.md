## Overall

| Metric | Before | After | Change |
|---|---|---|---|
| Requests | 11082 | 11556 | +4% |
| RPS (mean) | 28.1 | 29.5 | +5% |
| RPS (peak, 5-s window) | 64.2 | 64.2 | +0% |
| Latency avg, ms | 206.3 | 143.8 | -30% |
| Latency p95, ms | 821.3 | 1310.8 | +60% |
| Latency max, ms | 1511.0 | 2162.1 | +43% |
| Error rate, % | 0.00 | 0.00 | - |
| CPU api1 avg, % | 88.6 | 90.6 | +2% |
| RAM api1 avg, MiB | 89 | 92 | +4% |
| CPU db avg, % | 2.2 | 1.8 | -17% |
| RAM db avg, MiB | 54 | 62 | +14% |
| CPU redis avg, % | 0.9 | 1.0 | +15% |
| RAM redis avg, MiB | 4 | 5 | +6% |

## Per endpoint (avg / p95, ms)

| Endpoint | Before | After | avg | p95 |
|---|---|---|---|---|
| GET /auth/me | 211 / 812 | 75 / 439 | -65% | -46% |
| GET /stations | 167 / 713 | 9 / 40 | -95% | -94% |
| GET /vehicles | 188 / 815 | 9 / 40 | -95% | -95% |
| GET /vehicles/{id} | 188 / 817 | 71 / 417 | -62% | -49% |
| GET /vehicles/{id}/state | 193 / 829 | 8 / 50 | -96% | -94% |
| POST /auth/login | 291 / 892 | 691 / 1858 | +138% | +108% |

## Per load step (RPS; avg / p95, ms)

| VUs | RPS before | RPS after | Before | After |
|---|---|---|---|---|
| 10 | 7.5 | 7.5 | 20 / 100 | 14 / 71 |
| 25 | 17.8 | 18.3 | 75 / 401 | 18 / 81 |
| 50 | 35.9 | 37.2 | 58 / 221 | 25 / 144 |
| 100 | 56.5 | 60.4 | 435 / 1062 | 336 / 1713 |
