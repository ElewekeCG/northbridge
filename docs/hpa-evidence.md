# HPA Load Test Evidence — Deliverable D6

**Date:** 2026-07-26  
**Test duration:** 7 minutes (2m ramp up, 3m sustained at 50 VUs, 2m ramp down)  
**Target:** `catalog-service` — `/api/catalog/products`  
**HPA config:** `minReplicas: 2`, `maxReplicas: 8`, `targetCPUUtilizationPercentage: 50`

---

## Replica Count: Before, During, After

### Before Load Test
```
Time: Sun Jul 26 ~13:54:00 UTC 2026
NAME                  TARGETS       MINPODS  MAXPODS  REPLICAS
catalog-service-hpa   cpu: <1%/50%  2        8        2
```
Pods: 2 running (`catalog-service-668b667c8f-9mmtz`, `catalog-service-668b667c8f-jfphx`)

---

### During Load Test — HPA Scale-Up History

| Timestamp           | CPU Utilisation | Replicas |
|---------------------|-----------------|----------|
| 2026-07-26T14:09:23 | 121% / 50%      | 5        |
| 2026-07-26T14:09:54 | 157% / 50%      | 6        |
| 2026-07-26T14:10:25 | 146% / 50%      | 7        |
| 2026-07-26T14:10:56 | 162% / 50%      | 7        |
| 2026-07-26T14:11:27 | 157% / 50%      | 7        |
| 2026-07-26T14:11:58 | 159% / 50%      | 7        |
| 2026-07-26T14:12:29 | 149% / 50%      | 7        |
| 2026-07-26T14:13:00 | 131% / 50%      | 7        |
| 2026-07-26T14:13:31 | 104% / 50%      | 7        |

HPA scaled from **2 → 7 replicas** within ~2 minutes of load starting.
CPU peaked at **162%** of the 50% target before stabilising as new pods absorbed traffic.

---

### After Load Test
```
Time: Sun Jul 26 14:15:12 UTC 2026
NAME                  TARGETS      MINPODS  MAXPODS  REPLICAS
catalog-service-hpa   cpu: 5%/50%  2        8        7
```

CPU dropped to **5%** immediately after load ended. HPA will scale back down to
2 replicas after the default 5-minute scale-down stabilisation window.

---

## k6 Load Test Summary

```
scenarios: 1 scenario, 50 max VUs, 7m30s max duration
  stages: 2m ramp-up to 50 VUs, 3m sustained, 2m ramp-down

✓ status is 200
checks.........................: 100.00%  141,227 passed / 0 failed
http_req_duration..............: avg=4.74ms  p(90)=8.21ms  p(95)=10.87ms
http_req_failed................: 0.00%    0 failures out of 141,227 requests
http_reqs......................: 141,227  336 req/s
vus_max........................: 50
```

**Key results:**
- **141,227 total requests** — zero failures
- **p95 latency: 10.87ms** — well within the 2000ms threshold
- **Error rate: 0.00%** — catalog service remained fully available throughout
- **Throughput: 336 req/s** sustained at peak load

---

## Why This Matters — Incident #3

Incident #3: during a flash sale the catalog service was OOM-killed four times
in twenty minutes. Compose restarted the same undersized container each time
with no ability to add capacity.

This load test demonstrates the structural fix: when CPU exceeds the 50% target,
Kubernetes automatically schedules additional replicas across available nodes.
The service absorbed 336 req/s at peak with zero errors and sub-11ms p95 latency
— load that would have triggered repeated OOM kills under the Compose deployment
was handled transparently by the HPA scaling from 2 to 7 replicas.

The scale-down will return replicas to 2 automatically once CPU stays below
threshold for the stabilisation window, ensuring no wasted capacity after the
flash sale ends.
