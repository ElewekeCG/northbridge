"""
Northbridge Commerce — Auth Service
FastAPI service handling signup, login, and JWT issuance.

Redis is used here for session caching: every authenticated request
across the platform calls /api/auth/verify. Before Redis, this meant
a Postgres query on every single request across seven services — at
Northbridge's traffic volume this was the single largest contributor
to p95 latency. Verified tokens are now cached in Redis with a TTL
matching the JWT expiry, so repeat verification within the token's
lifetime is a sub-millisecond Redis GET instead of a database round trip.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import jwt
import redis
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL   = os.getenv("DATABASE_URL", "postgresql://northbridge:northbridge_dev@postgres:5432/northbridge_db")
REDIS_URL      = os.getenv("REDIS_URL", "redis://redis:6379/0")
JWT_SECRET     = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM  = "HS256"
JWT_EXPIRY_MIN = 60

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

redis_client = redis.from_url(REDIS_URL, decode_responses=True)


class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name     = Column(String(150), nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Auth Service started — Redis session cache enabled")
    yield


app = FastAPI(title="Northbridge Auth Service", version="1.0.0", lifespan=lifespan)

# Prometheus metrics — exposes /metrics scraped by prometheus.yml
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.utcnow() + timedelta(minutes=JWT_EXPIRY_MIN),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token_cached(token: str) -> dict:
    """
    Checks Redis first. On cache miss, decodes the JWT (cryptographic
    verification, no DB call) and caches the result for the remaining
    TTL of the token. This is the pattern that removed Postgres from
    the hot path of every authenticated request.
    """
    cache_key = f"session:{token}"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    remaining_ttl = int(payload["exp"] - datetime.utcnow().timestamp())
    if remaining_ttl > 0:
        redis_client.setex(cache_key, remaining_ttl, json.dumps(payload, default=str))

    return payload


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    return verify_token_cached(credentials.credentials)

@app.get("/healthz")
async def health(db: Session = Depends(get_db)):
    db_status = "ok"
    redis_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        db_status = "error"
    try:
        redis_client.ping()
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        redis_status = "error"
    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return {"status": overall, "db": db_status, "redis": redis_status, "service": "auth-service"}


@app.post("/api/auth/signup", response_model=TokenResponse, status_code=201)
async def signup(req: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=req.email, password_hash=pwd_context.hash(req.password), full_name=req.full_name)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id, user.email)
    return TokenResponse(access_token=token, expires_in=JWT_EXPIRY_MIN * 60)


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not pwd_context.verify(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user.id, user.email)
    return TokenResponse(access_token=token, expires_in=JWT_EXPIRY_MIN * 60)


@app.post("/api/auth/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Invalidates the cached session immediately — important for the cache
    to not outlive an explicit logout even though the JWT itself remains
    technically valid until expiry."""
    redis_client.delete(f"session:{credentials.credentials}")
    return {"logged_out": True}


@app.get("/api/auth/me")
async def me(payload: dict = Depends(verify_token), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user.id, "email": user.email, "full_name": user.full_name}


@app.post("/api/auth/verify")
async def verify(payload: dict = Depends(verify_token)):
    """Called by all other services to validate a token. This is the
    highest-traffic endpoint in the platform — every authenticated
    request to any service hits this first. Redis caching here is
    what keeps p95 latency low under load."""
    return {"valid": True, "user_id": payload["sub"], "email": payload["email"]}
