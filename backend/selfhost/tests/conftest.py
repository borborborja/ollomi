import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault(
    "OLLOMI_SECRET_KEY", "unit-test-instance-secret-not-for-deployment"
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "OLLOMI_DATABASE_URL", "sqlite:///" + str(tmp_path / "test.sqlite")
    )
    monkeypatch.setenv("OLLOMI_DATA_DIR", str(tmp_path / "data"))
    from selfhost.config import settings
    from selfhost.db import Base, User, engine, transaction
    from selfhost.security import passwords
    from selfhost import rate_limit

    settings.cache_clear()
    engine.cache_clear()
    Base.metadata.create_all(engine())
    monkeypatch.setattr(rate_limit, "limit", lambda *args: None)
    with transaction() as db:
        db.add(
            User(
                email="admin@test.local",
                name="Admin",
                admin=True,
                password_hash=passwords.hash("admin-password-123"),
            )
        )
    from selfhost.main import app

    with TestClient(app) as client:
        yield client
    engine().dispose()
    engine.cache_clear()
    settings.cache_clear()


@pytest.fixture
def admin(client):
    response = client.post(
        "/v1/auth/login",
        json={"email": "admin@test.local", "password": "admin-password-123"},
    )
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


@pytest.fixture
def other(client, admin):
    assert (
        client.post(
            "/v1/admin/users",
            headers=admin,
            json={"email": "user@test.local", "password": "other-password-123"},
        ).status_code
        == 201
    )
    response = client.post(
        "/v1/auth/login",
        json={"email": "user@test.local", "password": "other-password-123"},
    )
    return {"Authorization": "Bearer " + response.json()["access_token"]}
