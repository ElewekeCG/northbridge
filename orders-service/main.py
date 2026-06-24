"""
Northbridge Commerce — Orders Service
Orchestrates: validates user (Auth), checks/decrements stock (Catalog),
charges payment (Payments), reserves inventory (Inventory), and
triggers a notification (Notifications) on successful order.
"""

import os
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional, List

import httpx
from fastapi import FastAPI, HTTPException, Depends, Header
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL          = os.getenv("DATABASE_URL", "postgresql://northbridge:northbridge_dev@postgres:5432/northbridge_db")
AUTH_SERVICE          = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000")
CATALOG_SERVICE       = os.getenv("CATALOG_SERVICE_URL", "http://catalog-service:4000")
PAYMENTS_SERVICE      = os.getenv("PAYMENTS_SERVICE_URL", "http://payments-service:4001")
INVENTORY_SERVICE     = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8002")
NOTIFICATIONS_SERVICE = os.getenv("NOTIFICATIONS_SERVICE_URL", "http://notifications-service:4002")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Order(Base):
    __tablename__ = "orders"
    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, nullable=False, index=True)
    product_id  = Column(Integer, nullable=False)
    quantity    = Column(Integer, nullable=False)
    unit_price  = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    status      = Column(String(20), default="confirmed")
    created_at  = Column(DateTime, default=datetime.utcnow)


class OrderCreate(BaseModel):
    product_id: int
    quantity: int
    card_last4: str = "4242"


class OrderOut(BaseModel):
    id: int
    user_id: int
    product_id: int
    quantity: int
    unit_price: float
    total_price: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Orders Service started")
    yield


app = FastAPI(title="Northbridge Orders Service", version="1.0.0", lifespan=lifespan)

from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.post(f"{AUTH_SERVICE}/api/auth/verify", headers={"Authorization": authorization})
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Auth service unreachable")
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return resp.json()


@app.get("/healthz")
async def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok", "service": "orders-service"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "degraded", "db": "error"}


@app.post("/api/orders", response_model=OrderOut, status_code=201)
async def create_order(order: OrderCreate, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Fetch product
        product_resp = await client.get(f"{CATALOG_SERVICE}/api/catalog/products/{order.product_id}")
        if product_resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Product not found")
        product = product_resp.json()
        total = float(product["price"]) * order.quantity

        # 2. Reserve inventory
        reserve_resp = await client.post(
            f"{INVENTORY_SERVICE}/api/inventory/reserve",
            json={"product_id": order.product_id, "quantity": order.quantity},
        )
        if reserve_resp.status_code != 200:
            raise HTTPException(status_code=409, detail="Unable to reserve inventory")

        # 3. Charge payment
        payment_resp = await client.post(
            f"{PAYMENTS_SERVICE}/api/payments/charge",
            json={"amount": total, "card_last4": order.card_last4, "user_id": int(user["user_id"])},
        )
        if payment_resp.status_code != 200:
            # Roll back inventory reservation
            await client.post(
                f"{INVENTORY_SERVICE}/api/inventory/release",
                json={"product_id": order.product_id, "quantity": order.quantity},
            )
            raise HTTPException(status_code=402, detail="Payment failed")

        # 4. Decrement catalog stock count
        await client.patch(
            f"{CATALOG_SERVICE}/api/catalog/products/{order.product_id}/stock",
            json={"delta": -order.quantity},
        )

    db_order = Order(
        user_id=int(user["user_id"]),
        product_id=order.product_id,
        quantity=order.quantity,
        unit_price=float(product["price"]),
        total_price=total,
        status="confirmed",
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    # 5. Fire-and-forget notification — does not block order completion
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(
                f"{NOTIFICATIONS_SERVICE}/api/notifications/order-confirmed",
                json={"user_id": int(user["user_id"]), "order_id": db_order.id, "total": total},
            )
        except httpx.ConnectError:
            logger.warning("Notifications service unreachable — order still completed")

    logger.info(f"Order {db_order.id} created for user {user['user_id']}")
    return db_order


@app.get("/api/orders", response_model=List[OrderOut])
async def list_orders(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.user_id == int(user["user_id"])).order_by(Order.created_at.desc()).all()


@app.get("/api/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == int(user["user_id"])).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
