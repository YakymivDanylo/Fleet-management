# Lab 7 - how to run and demonstrate (Fleet Management)

Namespace of the app is `fleet`, API Service `fleet-management-api` (the lab text says `myapp`).
Rollout strategy: **canary** (lab 6) + `analysis` step. Reachability check: `kubectl get pods -A`.

## 0. Once: cluster and secrets
```bash
minikube start --cpus 4 --memory 8192          # an existing cluster: docker update --memory 8g --memory-swap 8g minikube
kubectl get applications -n argocd             # root, argo-rollouts, fleet-management  Synced/Healthy
kubectl create namespace monitoring
kubectl -n monitoring create secret generic grafana-admin \
  --from-literal=admin-user=admin --from-literal=admin-password='<password>'   # never in Git
# (fleet-secret for the app already exists: kubectl -n fleet get secret fleet-secret)
```
Monitoring (kps, loki, alloy) arrives from Git via the `root` app (3-7 min):
```bash
argocd app list            # or: kubectl -n argocd get applications  -> kps, loki, alloy Synced/Healthy
kubectl -n monitoring get pods
```

## 1. Port-forwards (three terminals)
```bash
kubectl -n monitoring port-forward svc/kps-grafana 3000:80          # admin / <password>
kubectl -n monitoring port-forward svc/kps-prometheus 9090:9090
kubectl -n monitoring port-forward svc/kps-alertmanager 9093:9093
```

## 2. Show: target in Prometheus + own metric
* http://localhost:9090/targets -> `serviceMonitor/fleet/fleet-management-api` **UP** (5 endpoints)
* Graph:
```
sum by (status) (rate(http_requests_total{namespace="fleet"}[1m]))
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{namespace="fleet"}[1m])))
```

## 3. Show: load on the dashboard
```bash
kubectl apply -f docs/lab7/load.yaml                       # steady background traffic
kubectl run hey --rm -it --restart=Never --image=williamyeh/hey -- \
  -z 3m -c 20 http://fleet-management-api.fleet.svc/version  # short heavy test
kubectl scale deploy/load --replicas=3                      # more traffic
```
Grafana -> Dashboards -> **Fleet Management - Observability** (range 15 min, refresh 10s):
requests/s, 5xx share, p95, CPU/memory per pod, logs.
Second change: `kubectl -n fleet delete pod <api-pod>` (pod drops and is replaced), or `replicaCount: 5 -> 8` in
`values-minikube.yaml` through Git (new pods appear on the CPU/memory panels).

## 4. Show: logs in Loki (Grafana -> Explore -> Loki)
```
{namespace="fleet", app="fleet-management"}
{namespace="fleet"} | json | status >= 500
{namespace="fleet"} | json | duration_ms > 20 | line_format "{{.route}} {{.duration_ms}}ms"
sum by (pod) (count_over_time({namespace="fleet"} | json | status >= 500 [1m]))
```

## 5. Bad release rolls back by itself (with load running)
```bash
kubectl argo rollouts get rollout fleet-management-api -n fleet --watch      # terminal A
kubectl -n fleet get analysisrun -w                                          # terminal B
# terminal C (Git): FAIL_RATE "0" -> "0.5" in charts/fleet-management/values-minikube.yaml
git commit -am "bad release: FAIL_RATE=0.5" && git push        # (via PR if main is protected)
```
Expected: `setWeight 20` -> pause 30s -> AnalysisRun **Failed** -> Rollout aborted/Degraded, canary pod scaled to 0,
traffic on stable. Dashboard: "5xx per pod" shows errors from one pod only, then they vanish. Loki:
`{namespace="fleet"} | json | status >= 500` shows only the new ReplicaSet pod (field `version`/`pod`).
```bash
kubectl -n fleet describe analysisrun <name>       # measured value + reason
git revert <commit with FAIL_RATE> && git push      # finish the rollback in Git
```
Good release: change `image.tag` -> AnalysisRun **Successful**, rollout reaches 100 %.

## 6. Alert (optional, d)
Prometheus -> Alerts -> `FleetHighErrorRate` Pending -> Firing. Because of `for: 1m` and the fast abort it may not fire;
to see it, temporarily set `rollout.analysis.enabled: false` and release the bad version fully.

## 7. Useful PromQL/LogQL on request
```
sum(rate(http_requests_total{namespace="fleet",status=~"5.."}[1m])) / sum(rate(http_requests_total{namespace="fleet"}[1m]))
sum by (pod) (rate(http_requests_total{namespace="fleet",status=~"5.."}[1m]))
sum by (route) (rate(http_requests_total{namespace="fleet"}[5m]))
{namespace="fleet"} | json | level="ERROR"
```
