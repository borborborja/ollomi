"""Tests for the POST /v1/auth/password/reset endpoint."""

import secrets
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture
def reset_client(client):
    from selfhost import password

    app = FastAPI()
    app.include_router(password.router)
    with TestClient(app) as mounted:
        # Reuse the DB and env prepared by the shared `client` fixture.
        yield client, mounted


def _create_user(client, admin, email, password="old-password-123"):
    assert (
        client.post(
            "/v1/admin/users",
            headers=admin,
            json={"email": email, "password": password},
        ).status_code
        == 201
    )


def _insert_reset(email, *, token=None, expires=None, used_at=None):
    from selfhost.db import PasswordReset, User, now, transaction
    from selfhost.security import digest

    token = token or secrets.token_urlsafe(32)
    with transaction() as db:
        user = db.scalar(select(User).where(User.email == email))
        db.add(
            PasswordReset(
                user_id=user.id,
                token_hash=digest(token),
                expires_at=expires or now() + timedelta(minutes=30),
                used_at=used_at,
            )
        )
    return token


def test_reset_valid_token_changes_password_and_allows_new_login(reset_client, admin):
    shared, mounted = reset_client
    _create_user(shared, admin, "user@test.local", password="old-password-123")
    token = _insert_reset("user@test.local")

    response = mounted.post(
        "/v1/auth/password/reset",
        json={"token": token, "password": "new-password-456"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "access_token" not in response.text

    # Old password no longer works; the new one does.
    assert shared.post(
        "/v1/auth/login", json={"email": "user@test.local", "password": "old-password-123"}
    ).status_code == 401
    assert shared.post(
        "/v1/auth/login", json={"email": "user@test.local", "password": "new-password-456"}
    ).status_code == 200


def test_reset_reused_token_returns_generic_400(reset_client, admin):
    shared, mounted = reset_client
    _create_user(shared, admin, "user@test.local")
    token = _insert_reset("user@test.local")

    first = mounted.post(
        "/v1/auth/password/reset",
        json={"token": token, "password": "new-password-456"},
    )
    assert first.status_code == 200
    second = mounted.post(
        "/v1/auth/password/reset",
        json={"token": token, "password": "another-password-789"},
    )
    assert second.status_code == 400
    assert second.json()["detail"] == "Invalid or expired reset token"


def test_reset_expired_token_returns_generic_400(reset_client, admin):
    shared, mounted = reset_client
    _create_user(shared, admin, "user@test.local")
    from selfhost.db import now

    token = _insert_reset("user@test.local", expires=now() - timedelta(minutes=1))

    response = mounted.post(
        "/v1/auth/password/reset",
        json={"token": token, "password": "new-password-456"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired reset token"


def test_reset_unknown_token_returns_generic_400(reset_client):
    _, mounted = reset_client
    response = mounted.post(
        "/v1/auth/password/reset",
        json={"token": secrets.token_urlsafe(32), "password": "new-password-456"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired reset token"


def test_reset_short_password_returns_422_and_keeps_token_usable(reset_client, admin):
    shared, mounted = reset_client
    _create_user(shared, admin, "user@test.local")
    token = _insert_reset("user@test.local")

    response = mounted.post(
        "/v1/auth/password/reset",
        json={"token": token, "password": "short"},
    )
    assert response.status_code == 422

    # Token still usable after a failed validation.
    retry = mounted.post(
        "/v1/auth/password/reset",
        json={"token": token, "password": "valid-password-456"},
    )
    assert retry.status_code == 200
    assert shared.post(
        "/v1/auth/login", json={"email": "user@test.local", "password": "valid-password-456"}
    ).status_code == 200


def test_reset_disabled_user_returns_same_generic_400(reset_client, admin):
    shared, mounted = reset_client
    _create_user(shared, admin, "disabled@test.local")
    token = _insert_reset("disabled@test.local")

    from selfhost.db import User, transaction

    with transaction() as db:
        user = db.scalar(select(User).where(User.email == "disabled@test.local"))
        user.enabled = False

    response = mounted.post(
        "/v1/auth/password/reset",
        json={"token": token, "password": "new-password-456"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired reset token"


def test_reset_env_owned_admin_returns_same_generic_400(reset_client, admin, monkeypatch):
    shared, mounted = reset_client
    # The shared `client` fixture seeds admin@test.local; mark it env-owned.
    monkeypatch.setenv("OLLOMI_ADMIN_EMAIL", "admin@test.local")
    monkeypatch.setenv("OLLOMI_ADMIN_PASSWORD", "bootstrap-secret-123")
    token = _insert_reset("admin@test.local")

    response = mounted.post(
        "/v1/auth/password/reset",
        json={"token": token, "password": "new-password-456"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired reset token"


def test_reset_error_message_is_identical_across_failures(reset_client, admin, monkeypatch):
    shared, mounted = reset_client
    _create_user(shared, admin, "user@test.local")
    _create_user(shared, admin, "disabled@test.local")
    from selfhost.db import User, now, transaction

    expired_token = _insert_reset("user@test.local", expires=now() - timedelta(minutes=1))
    with transaction() as db:
        user = db.scalar(select(User).where(User.email == "disabled@test.local"))
        user.enabled = False
    disabled_token = _insert_reset("disabled@test.local")
    monkeypatch.setenv("OLLOMI_ADMIN_EMAIL", "admin@test.local")
    monkeypatch.setenv("OLLOMI_ADMIN_PASSWORD", "bootstrap-secret-123")
    env_token = _insert_reset("admin@test.local")

    bodies = set()
    for token in (
        expired_token,
        disabled_token,
        env_token,
        secrets.token_urlsafe(32),  # unknown
    ):
        response = mounted.post(
            "/v1/auth/password/reset",
            json={"token": token, "password": "new-password-456"},
        )
        assert response.status_code == 400
        bodies.add(response.json()["detail"])
    assert bodies == {"Invalid or expired reset token"}


def test_reset_revokes_sessions_and_mcp_credentials(reset_client, admin, other):
    shared, mounted = reset_client
    # `other` logs in user@test.local with a live session; create an MCP key.
    created = shared.post(
        "/v1/mcp/keys",
        headers=other,
        json={"name": "cli", "scopes": ["records:read"]},
    )
    assert created.status_code == 200
    token = _insert_reset("user@test.local")

    response = mounted.post(
        "/v1/auth/password/reset",
        json={"token": token, "password": "new-password-456"},
    )
    assert response.status_code == 200

    from selfhost.db import McpApiKey, Session, User, transaction

    with transaction() as db:
        user = db.scalar(select(User).where(User.email == "user@test.local"))
        sessions = db.scalars(select(Session).where(Session.user_id == user.id)).all()
        keys = db.scalars(select(McpApiKey).where(McpApiKey.user_id == user.id)).all()
    assert sessions and all(session.revoked for session in sessions)
    assert keys and all(key.revoked for key in keys)

    # The old access token is rejected.
    probe = shared.get("/v1/auth/me", headers=other)
    assert probe.status_code == 401
