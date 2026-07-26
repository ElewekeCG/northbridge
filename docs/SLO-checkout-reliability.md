# SLO-001: Checkout Flow Reliability

**Status:** Accepted  
**Owner:** Platform Engineering  
**Review cadence:** Monthly  
**Effective date:** 2026-07-26  

---

## Service Level Objective

> **99.5% of checkout requests (POST /api/orders) must complete successfully
> in under 400ms, measured over a rolling 30-day window.**

A request is counted as **good** if and only if both conditions are true:
1. The HTTP response code is `2xx` or `402` (a legitimate payment decline is not
   a platform error — it is correct behaviour)
2. The response is delivered within **400ms** end-to-end (measured at the
   orders-service, from request receipt to response sent)

A request is counted as **bad** if either:
- The response code is `5xx` (server error), or
- The response takes longer than 400ms regardless of status code

---

## Why These Numbers

**99.5%** — not 99.9%. The difference matters:

| SLO    | Allowed downtime / 30 days | Error budget |
|--------|---------------------------|--------------|
| 99.0%  | 7h 18m                    | 1.0%         |
| 99.5%  | 3h 39m                    | 0.5%         |
| 99.9%  | 43m 49s                   | 0.1%         |
| 99.99% | 4m 23s                    | 0.01%        |

99.9% is aspirational for a platform that has experienced six availability
incidents in two quarters, one of which was a 47-minute undetected outage
(incident #4 from the incident history). Setting an unachievable SLO creates
alert fatigue — every burn rate alert fires constantly and engineers stop
responding. 99.5% is honest about where the platform is today while creating
genuine accountability for improvement.

**400ms** — not 200ms or 1000ms. The checkout flow calls five downstream
services in sequence: auth → catalog → inventory → payments → notifications.
The load test showed p95 latency of 10.87ms per request at 50 VUs on the
catalog endpoint alone. A realistic end-to-end budget across five services
with network overhead is:

| Service call         | p95 budget |
|---------------------|-----------|
| auth/verify          | 20ms      |
| catalog/products/:id | 15ms      |
| inventory/reserve    | 25ms      |
| payments/charge      | 150ms     |
| notifications        | 30ms      |
| orders DB write      | 20ms      |
| Network overhead     | 50ms      |
| **Total**            | **310ms** |

400ms gives 90ms of headroom above the p95 sum — enough to absorb normal
variance without burning budget on every slightly slow payment processor
response.

---

## Error Budget Arithmetic

### Step 1 — Total requests in 30 days

From load test data: the platform sustains approximately **336 requests/second**
at peak. Assuming a realistic traffic model:

- Peak hours (8h/day): 336 req/s
- Off-peak hours (16h/day): 50 req/s

Daily request volume:
```
Peak:     336 req/s × 3600s × 8h  =  9,676,800 requests
Off-peak:  50 req/s × 3600s × 16h =  2,880,000 requests
Daily total:                          12,556,800 requests
```

30-day total:
```
12,556,800 × 30 = 376,704,000 requests (~376.7 million)
```

For a more conservative baseline matching current actual traffic
(the load test was synthetic — real traffic is lower):

Assume **500,000 checkout requests per 30 days** as the current baseline.
This is the number used for error budget calculations below. Revisit when
real traffic instrumentation from Prometheus is available.

### Step 2 — Error budget percentage

```
SLO target:    99.5%
Error budget:  100% - 99.5% = 0.5%
```

### Step 3 — Allowed bad requests

```
Total requests (30 days):  500,000
Error budget (0.5%):       500,000 × 0.005 = 2,500 bad requests
```

**The error budget is 2,500 bad requests per 30-day window.**

Once 2,500 requests have either returned a 5xx error or exceeded 400ms,
the error budget is exhausted and no further reliability risk should be
taken (no deployments, no experiments) until the window resets.

### Step 4 — Error budget in time terms

At **500,000 requests / 30 days**:
```
Requests per minute: 500,000 / (30 × 24 × 60) = ~11.6 req/min
```

At a complete outage (100% of requests bad):
```
Time to exhaust budget: 2,500 / 11.6 = ~215 minutes = 3h 35m
```

This means a total platform outage would exhaust the error budget in
**3 hours 35 minutes**. Any outage longer than this in a 30-day window
means the SLO has been breached.

### Step 5 — Burn rate thresholds for alerting

| Burn rate | Budget consumed | Alert window | Meaning |
|-----------|----------------|--------------|---------|
| 14.4×     | 100% in 2h     | 1h           | Page immediately — critical outage |
| 6×        | 100% in 5h     | 6h           | Page — severe degradation |
| 3×        | 100% in 10h    | 3h           | Ticket — elevated error rate |
| 1×        | 100% in 30d    | 6h           | Informational — on track to exhaust |

These burn rates map directly to Prometheus alerting rules using the
`http_request_duration_seconds` histogram already instrumented in every service.

---

## PromQL Expressions

### Current error rate (5xx):
```promql
sum(rate(http_request_duration_seconds_count{job="orders-service",status_code=~"5.."}[5m]))
/
sum(rate(http_request_duration_seconds_count{job="orders-service"}[5m]))
```

### Current latency SLO compliance (requests under 400ms):
```promql
sum(rate(http_request_duration_seconds_bucket{job="orders-service",le="0.4"}[5m]))
/
sum(rate(http_request_duration_seconds_count{job="orders-service"}[5m]))
```

### 30-day error budget remaining:
```promql
1 - (
  sum(increase(http_request_duration_seconds_count{job="orders-service",status_code=~"5.."}[30d]))
  +
  sum(increase(http_request_duration_seconds_count{job="orders-service"}[30d]))
  -
  sum(increase(http_request_duration_seconds_bucket{job="orders-service",le="0.4"}[30d]))
)
/
(sum(increase(http_request_duration_seconds_count{job="orders-service"}[30d])) * 0.005)
```

---

## What Happens When Budget Is Exhausted

1. **Freeze deployments** — no new code ships to production until the window
   resets or the error rate recovers sufficiently.
2. **Freeze experiments** — no A/B tests, feature flags, or infrastructure
   changes that carry reliability risk.
3. **Engineering focus shifts** to reliability work only — incident
   post-mortems, fixing the root cause of budget burn, adding test coverage.
4. **Stakeholder notification** — product and engineering leadership are
   informed that the SLO has been breached and given a timeline for recovery.

This is the contractual consequence of the error budget framework. Without
consequences, the SLO is a number on a document, not a commitment.

---

## Relationship to Incident History

| Incident | Budget impact |
|----------|--------------|
| #1 — Maintenance reboot (6 min outage) | 6 min × 11.6 req/min = ~70 bad requests = 2.8% of monthly budget |
| #3 — Catalog OOM-killed 4× during flash sale | At 6× normal traffic for 20 min = significant burn, likely 15-20% of budget |
| #4 — 47-minute undetected outage | 47 × 11.6 = ~545 bad requests = 21.8% of monthly budget |

Incident #4 alone would have consumed 21.8% of the monthly error budget.
Three incidents of similar severity in one month would exhaust the budget
entirely and trigger a deployment freeze — exactly the accountability
mechanism that the error budget framework is designed to create.

---

## Review and Tightening Schedule

| Date       | Target | Rationale |
|------------|--------|-----------|
| 2026-07-26 | 99.5%  | Baseline — honest about current platform maturity |
| 2026-10-26 | 99.7%  | After EKS migration and HPA are stable for one quarter |
| 2027-01-26 | 99.9%  | After full observability stack proven in production |

SLO tightening is only appropriate when the previous target has been met
comfortably for a full quarter with budget to spare.
