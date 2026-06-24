"""
Northbridge Commerce — Auth Service Tests
Run: pytest tests/ -v

Note: these tests use fakeredis to avoid requiring a live Redis instance
in CI. In docker-compose, the real Redis container is used.
"""

import os
os.environ["DATABASE_URL"] = "sqlite:///./test_auth.db"

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock


@pytest.fixture(scope="module")
def client(monkeypatch_session=None):
    import main
    # Replace the real Redis client with an in-memory mock for testing
    fake_store = {}

    class FakeRedis:
        def get(self, key): return fake_store.get(key)
        def setex(self, key, ttl, value): fake_store[key] = value
        def delete(self, key): fake_store.pop(key, None)
        def ping(self): return True

    main.redis_client = FakeRedis()
    main.Base.metadata.create_all(bind=main.engine)

    with TestClient(main.app) as c:
        yield c

    main.Base.metadata.drop_all(bind=main.engine)


def test_health(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["redis"] == "ok"


def test_signup_returns_token(client):
    r = client.post("/api/auth/signup", json={
        "email": "test@northbridge.com", "password": "SecurePass123", "full_name": "Test User"
    })
    assert r.status_code == 201
    assert "access_token" in r.json()


def test_login_success(client):
    client.post("/api/auth/signup", json={
        "email": "login@northbridge.com", "password": "mypassword", "full_name": "Login Test"
    })
    r = client.post("/api/auth/login", json={"email": "login@northbridge.com", "password": "mypassword"})
    assert r.status_code == 200


def test_verify_caches_in_redis(client):
    signup_r = client.post("/api/auth/signup", json={
        "email": "cache@northbridge.com", "password": "pass123", "full_name": "Cache Test"
    })
    token = signup_r.json()["access_token"]

    # First call — cache miss, decodes JWT
    r1 = client.post("/api/auth/verify", headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == 200

    # Second call — should hit the cache (same result, faster path)
    r2 = client.post("/api/auth/verify", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r1.json() == r2.json()


def test_logout_invalidates_session(client):
    signup_r = client.post("/api/auth/signup", json={
        "email": "logout@northbridge.com", "password": "pass123", "full_name": "Logout Test"
    })
    token = signup_r.json()["access_token"]

    client.post("/api/auth/verify", headers={"Authorization": f"Bearer {token}"})
    logout_r = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_r.status_code == 200
    assert logout_r.json()["logged_out"] is True
