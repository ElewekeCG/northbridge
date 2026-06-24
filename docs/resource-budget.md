# Resource Budget & Instance Size Rationale

## Instance: t3.medium (2 vCPU, 4 GB RAM)

## Memory Allocation

| Service               | Limit  | Justification                                              |
|-----------------------|--------|------------------------------------------------------------|
| postgres              | 512 MB | Largest single allocation; shared by all services          |
| redis                 | 160 MB | Capped internally at 128 MB via maxmemory; 32 MB overhead  |
| orders-service        | 256 MB | Hub service; holds connections to 5 downstream services    |
| auth-service          | 192 MB | Hot path on every request; session verification overhead   |
| catalog-service       | 192 MB | Node.js baseline + Redis client + product data             |
| inventory-service     | 192 MB | Python/FastAPI baseline + DB connection pool               |
| payments-service      | 192 MB | Node.js baseline; handles sensitive checkout flow          |
| notifications-service | 128 MB | Low-traffic; fire-and-forget after order events            |
| analytics-service     | 128 MB | Read-only, non-hot-path; no caching layer by design        |
| frontend              |  64 MB | nginx serving a static HTML file; minimal footprint        |
| **Total (containers)**| **2,016 MB** |                                                       |

## OS & Daemon Headroom

| Component        | Estimate |
|------------------|----------|
| Ubuntu 22.04 OS  | ~400 MB  |
| Docker daemon    | ~150 MB  |
| Kernel / buffers |  ~50 MB  |
| **Total reserved**| **~600 MB** |

## Summary

| Budget line         | Memory     |
|---------------------|------------|
| Container limits    | 2,016 MB   |
| OS + Docker         |   600 MB   |
| **Total committed** | **2,616 MB** |
| t3.medium available | 4,096 MB   |
| **Free headroom**   | **~1,480 MB (~36%)** |

---

## Why t3.medium — Not Smaller, Not Larger

### Why not t3.small (2 GB)?

A t3.small would technically launch all containers but would leave under 100 MB of
unallocated RAM. In practice this means:

- The OS OOM killer would terminate containers under any traffic spike
- PostgreSQL's shared_buffers would be squeezed, degrading query performance
- There would be no room to `docker compose up` a new image during a rolling
  deployment without the old container still occupying memory

t3.small is a false economy: it costs ~$0.023/hr vs ~$0.047/hr for t3.medium,
but a single OOM-induced outage costs more in lost revenue and engineering time
than months of the instance price difference.

### Why not t3.large or above (8 GB+)?

The current workload has no demonstrated need for it. The 1.4 GB of free headroom
on a t3.medium is sufficient to:

- Absorb realistic traffic spikes (the incident history shows 6x peak, not 60x)
- Run a rolling deploy without downtime
- Leave breathing room for the Docker layer cache

Provisioning a larger instance before the workload justifies it violates the
principle of sizing to measured need. When analytics, Prometheus, or Grafana are
added and memory pressure is observed (via `docker stats` or Grafana dashboards),
upgrading to t3.large is a one-command change in Terraform or the AWS console.
The architecture does not need to change — only the instance type.

### Why t3 (burstable) rather than m6i (general purpose)?

At Northbridge's current scale, CPU usage is not sustained. Requests are
short-lived (auth checks, catalog reads, order writes). The t3 burstable model
accumulates CPU credits during idle periods and spends them during traffic spikes —
exactly the pattern of a growing e-commerce platform that is busy for hours at a
time, not continuously saturated. An m6i instance at equivalent memory costs
roughly 2x more per hour for CPU headroom that the workload does not yet need.

The decision should be revisited if CPU credit balance is consistently at zero
(visible in CloudWatch as `CPUCreditBalance`), which would indicate sustained
load that justifies a fixed-performance instance.

---

## Upgrade Trigger Criteria

The instance should be upsized when **any two** of the following are true:

- Free memory headroom falls below 512 MB under normal (non-peak) load
- `CPUCreditBalance` in CloudWatch is consistently below 20
- p99 response time on `/api/orders` exceeds 500ms without an identified
  application-layer cause
- A new service (e.g. Prometheus + Grafana stack) is added that requires
  more than 300 MB combined

At that point, upgrade to **t3.large (8 GB)** before considering a move to
fixed-performance compute.