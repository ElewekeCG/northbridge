"""
Northbridge Commerce — Analytics Service
Aggregates order data for the internal operations dashboard. Read-heavy,
read-only service — queries Postgres directly since aggregate queries
over the orders table are not on the hot path the way auth verification
or catalog reads are. No Redis caching here; this is a deliberate
architectural choice interns should be able to articulate: not every
service needs caching, only the ones with proven hot-path read pressure.
"""

import os
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://northbridge:northbridge_dev@postgres:5432/northbridge_db")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Analytics Service started")
    yield


app = FastAPI(title="Northbridge Analytics Service", version="1.0.0", lifespan=lifespan)

from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/api/auth/healthz")
async def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok", "service": "analytics-service"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "degraded", "db": "error"}


@app.get("/api/analytics/summary")
async def summary(db: Session = Depends(get_db)):
    """Returns aggregate order metrics. Queries the orders table directly
    — orders is created by orders-service in the same Postgres instance."""
    try:
        total_orders = db.execute(text("SELECT COUNT(*) FROM orders")).scalar() or 0
        total_revenue = db.execute(text("SELECT COALESCE(SUM(total_price), 0) FROM orders")).scalar() or 0
        avg_order_value = db.execute(text("SELECT COALESCE(AVG(total_price), 0) FROM orders")).scalar() or 0

        return {
            "total_orders":     int(total_orders),
            "total_revenue":    round(float(total_revenue), 2),
            "avg_order_value":  round(float(avg_order_value), 2),
            "generated_at":     datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Analytics query failed (orders table may not exist yet): {e}")
        return {"total_orders": 0, "total_revenue": 0, "avg_order_value": 0, "generated_at": datetime.utcnow().isoformat()}


@app.get("/api/analytics/daily")
async def daily_orders(db: Session = Depends(get_db)):
    """Order count and revenue for the last 7 days."""
    try:
        rows = db.execute(text("""
            SELECT DATE(created_at) as day, COUNT(*) as orders, COALESCE(SUM(total_price),0) as revenue
            FROM orders
            WHERE created_at >= :since
            GROUP BY DATE(created_at)
            ORDER BY day DESC
        """), {"since": datetime.utcnow() - timedelta(days=7)}).fetchall()

        return {
            "days": [
                {"date": str(r[0]), "orders": r[1], "revenue": round(float(r[2]), 2)}
                for r in rows
            ]
        }
    except Exception as e:
        logger.error(f"Daily analytics query failed: {e}")
        return {"days": []}
