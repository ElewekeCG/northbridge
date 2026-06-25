"""
Northbridge Commerce — Inventory Service
Tracks reserved stock separately from catalog stock counts. When an
order begins, inventory is "reserved" (held) before payment completes.
If payment fails, the reservation is released back to available stock.
This two-phase reserve/release pattern prevents overselling during the
window between a customer starting checkout and payment confirming.
"""

import os
import logging
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, Integer, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://northbridge:northbridge_dev@postgres:5432/northbridge_db")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Reservation(Base):
    __tablename__ = "inventory_reservations"
    id          = Column(Integer, primary_key=True, index=True)
    product_id  = Column(Integer, nullable=False, index=True)
    quantity    = Column(Integer, nullable=False)
    status      = Column(Integer, default=1)  # 1=reserved, 0=released
    created_at  = Column(DateTime, default=datetime.utcnow)


class ReserveRequest(BaseModel):
    product_id: int
    quantity: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Inventory Service started")
    yield


app = FastAPI(title="Northbridge Inventory Service", version="1.0.0", lifespan=lifespan)

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
        return {"status": "ok", "db": "ok", "service": "inventory-service"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "degraded", "db": "error"}


@app.post("/api/inventory/reserve", status_code=200)
async def reserve(req: ReserveRequest, db: Session = Depends(get_db)):
    reservation = Reservation(product_id=req.product_id, quantity=req.quantity, status=1)
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    logger.info(f"Reserved {req.quantity} units of product {req.product_id}")
    return {"reservation_id": reservation.id, "status": "reserved"}


@app.post("/api/inventory/release", status_code=200)
async def release(req: ReserveRequest, db: Session = Depends(get_db)):
    reservation = (
        db.query(Reservation)
        .filter(Reservation.product_id == req.product_id, Reservation.status == 1)
        .order_by(Reservation.created_at.desc())
        .first()
    )
    if reservation:
        reservation.status = 0
        db.commit()
    logger.info(f"Released reservation for product {req.product_id}")
    return {"status": "released"}


@app.get("/api/inventory/reservations")
async def list_reservations(db: Session = Depends(get_db)):
    rows = db.query(Reservation).order_by(Reservation.created_at.desc()).limit(50).all()
    return [{"id": r.id, "product_id": r.product_id, "quantity": r.quantity, "status": r.status} for r in rows]
