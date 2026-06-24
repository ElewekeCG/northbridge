# Northbridge Commerce — Senior DevOps Project

**Amdari Internship Programme | DevOps Track — Senior Cohort**

**Project:** Production E-Commerce Platform Engineering with Traefik, Redis Caching, and Full-Stack Observability for Northbridge Commerce

---

## Read ADR-001 Before You Touch Anything

`docs/ADR-001-redis-introduction.md` explains why Redis was introduced, where it is used,
where it is deliberately not used, and the trade-offs accepted. You will be asked to defend
this document verbally at the end of the project without re-reading it. Read it now.

---

## What You Have Been Given vs What You Build

| File / Directory | Status | Your Task |
|---|---|---|
| All service `main.py` and `app.js` files | Given | Do not modify |
| All `requirements.txt` and `package.json` | Given | Do not modify |
| All `Dockerfile`s | Given | Do not modify |
| `frontend/index.html` | Given | Do not modify |
| `docs/ADR-001-redis-introduction.md` | Given | Read first |
| `monitoring/grafana/dashboards/northbridge-overview.json` | Given | Mount it correctly |
| `scripts/load-test.js` | Given | Use for D4 evidence |
| `.env.example` | Given | Copy to `.env`, fill in values |
| `docker-compose.yml` | Stub | You write this |
| `traefik/traefik.yml` | Stub | You write this |
| `monitoring/prometheus/prometheus.yml` | Stub | You write this |
| `monitoring/prometheus/alert_rules.yml` | Stub | You write this |
| `monitoring/alertmanager/alertmanager.yml` | Stub | You write this |
| `monitoring/grafana/provisioning/**` | Stubs | You write these |
| `scripts/backup_db.sh` | Stub | You write this |
| `scripts/restore_db.sh` | Stub | You write this |
| `scripts/server_setup.sh` | Stub | You write this |
| `.github/workflows/ci.yml` | Stub | You write this |
| `.github/workflows/deploy.yml` | Stub | You write this |

---

## Architecture

```
Browser -> DNS -> EC2 (t3.medium)
             -> Traefik (automatic TLS via Let's Encrypt, label-based routing)
                 -> shop.yourdomain.com/              -> frontend
                 -> shop.yourdomain.com/api/auth      -> auth-service     (Redis: session cache)
                 -> shop.yourdomain.com/api/catalog   -> catalog-service  (Redis: product cache)
                 -> shop.yourdomain.com/api/orders    -> orders-service
                 -> shop.yourdomain.com/api/payments  -> payments-service
                 -> shop.yourdomain.com/api/inventory -> inventory-service
                 -> shop.yourdomain.com/api/notifications -> notifications-service
                 -> shop.yourdomain.com/api/analytics -> analytics-service

  traefik.yourdomain.com    -> Traefik dashboard (basic auth)
  metrics.yourdomain.com    -> Prometheus (basic auth)
  dashboard.yourdomain.com  -> Grafana
```

## Services

| Service | Stack | Port | Redis? |
|---|---|---|---|
| auth-service | FastAPI | 8000 | Session cache |
| catalog-service | Express | 4000 | Product cache |
| orders-service | FastAPI | 8001 | No |
| payments-service | Express | 4001 | No |
| inventory-service | FastAPI | 8002 | No |
| notifications-service | Express | 4002 | No |
| analytics-service | FastAPI | 8003 | No — deliberately, read ADR-001 |
| frontend | Nginx static | 80 | No |

## Getting Started

```bash
git clone <your-fork-url> northbridge-commerce
cd northbridge-commerce
cp .env.example .env
nano .env
# Start with docker-compose.yml — read the stub comments carefully
```

## Resource Budget

Before deploying, sum the memory limits you assign to each container.
Total must fit within ~3.5GB on the t3.medium. Document it in /docs/resource-budget.md.

## Required GitHub Secrets

AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, ECR_REGISTRY
EC2_HOST, EC2_USER, EC2_SSH_KEY
POSTGRES_PASSWORD, REDIS_PASSWORD, JWT_SECRET
TRAEFIK_DASHBOARD_AUTH, GRAFANA_ADMIN_PASSWORD
SLACK_WEBHOOK_URL, BACKUP_S3_BUCKET
