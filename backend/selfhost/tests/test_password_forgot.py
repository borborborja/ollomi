"""Tests for the POST /v1/auth/password/forgot endpoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture
def forgot_client(client, monkeypatch):
    monkeypatch.setenv("OLLOMI_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("OLLOMI_SMTP_FROM", "Ollomi <no-reply@example.org>")
    monkeypatch.setenv("OLLOMI_PUBLIC_URL", "https://ollomi.test/")
    from selfhost.config import settings
    from selfhost import password

    settings.cache_clear()
    app = FastAPI()
    app.include_router(password.router)
    try:
        with TestClient(app) as mounted:
            # Reuse the DB and env prepared by the shared `client` fixture.
            yield client, mounted
    finally:
        settings.cache_clear()


def _capture_mailer(monkeypatch):
    calls = []
    from selfhost import mail

    def capture(to, link, language):
        calls.append((to, link, language))
        return True

    monkeypatch.setattr(mail, "send_password_reset_email", capture)
    return calls


def _create_user(client, admin, email, password="some-password-123"):
    assert (
        client.post(
            "/v1/admin/users",
            headers=admin,
            json={"email": email, "password": password},
        ).status_code
        == 201
    )


def test_forgot_existing_enabled_user_creates_token_and_sends_mail(forgot_client, admin, monkeypatch):
    shared, mounted = forgot_client
    _create_user(shared, admin, "user@test.local")
    calls = _capture_mailer(monkeypatch)
    response = mounted.post("/v1/auth/password/forgot", json={"email": "user@test.local"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    from selfhost.db import PasswordReset, transaction

    with transaction() as db:
        rows = db.scalars(select(PasswordReset)).all()
    assert len(rows) == 1
    assert len(calls) == 1
    to, link, language = calls[0]
    assert to == "user@test.local"
    assert link.startswith("https://ollomi.test/reset-password#token=")
    token = link.split("token=", 1)[1]
    assert rows[0].token_hash != token
    from selfhost.security import digest

    assert rows[0].token_hash == digest(token)
    assert language == ""


def test_forgot_unknown_email_returns_same_body_and_no_side_effects(forgot_client, monkeypatch):
    _, mounted = forgot_client
    calls = _capture_mailer(monkeypatch)
    response = mounted.post("/v1/auth/password/forgot", json={"email": "ghost@test.local"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    from selfhost.db import PasswordReset, transaction

    with transaction() as db:
        assert db.scalars(select(PasswordReset)).all() == []
    assert calls == []


def test_forgot_disabled_user_returns_same_body_and_no_mail(forgot_client, admin, monkeypatch):
    shared, mounted = forgot_client
    _create_user(shared, admin, "disabled@test.local")
    from selfhost.db import User, transaction

    with transaction() as db:
        user = db.scalar(select(User).where(User.email == "disabled@test.local"))
        user.enabled = False

    calls = _capture_mailer(monkeypatch)
    response = mounted.post("/v1/auth/password/forgot", json={"email": "disabled@test.local"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    from selfhost.db import PasswordReset

    with transaction() as db:
        assert db.scalars(select(PasswordReset)).all() == []
    assert calls == []


def test_forgot_env_owned_admin_returns_same_body_and_no_mail(forgot_client, monkeypatch):
    _, mounted = forgot_client
    # The shared `client` fixture seeds admin@test.local; mark it env-owned.
    calls = _capture_mailer(monkeypatch)
    monkeypatch.setenv("OLLOMI_ADMIN_EMAIL", "admin@test.local")
    monkeypatch.setenv("OLLOMI_ADMIN_PASSWORD", "bootstrap-secret-123")
    response = mounted.post("/v1/auth/password/forgot", json={"email": "admin@test.local"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    from selfhost.db import PasswordReset, transaction

    with transaction() as db:
        assert db.scalars(select(PasswordReset)).all() == []
    assert calls == []

    # Without OLLOMI_ADMIN_PASSWORD the account is not env-owned, so a mail is sent.
    monkeypatch.delenv("OLLOMI_ADMIN_PASSWORD")
    response = mounted.post("/v1/auth/password/forgot", json={"email": "admin@test.local"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(calls) == 1


def test_forgot_without_smtp_configured_returns_503(forgot_client, monkeypatch):
    _, mounted = forgot_client
    monkeypatch.delenv("OLLOMI_SMTP_HOST")
    monkeypatch.delenv("OLLOMI_SMTP_FROM")
    from selfhost.config import settings

    settings.cache_clear()
    try:
        response = mounted.post("/v1/auth/password/forgot", json={"email": "user@test.local"})
        assert response.status_code == 503
        assert response.json()["detail"] == "Email delivery is not configured"
    finally:
        settings.cache_clear()


def test_forgot_twice_invalidates_first_token(forgot_client, admin, monkeypatch):
    shared, mounted = forgot_client
    _create_user(shared, admin, "user@test.local")
    calls = _capture_mailer(monkeypatch)
    first = mounted.post("/v1/auth/password/forgot", json={"email": "user@test.local"})
    second = mounted.post("/v1/auth/password/forgot", json={"email": "user@test.local"})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"status": "ok"}
    assert len(calls) == 2
    first_link, second_link = calls[0][1], calls[1][1]

    from selfhost.db import PasswordReset, transaction
    from selfhost.security import digest

    first_token = first_link.split("token=", 1)[1]
    second_token = second_link.split("token=", 1)[1]
    assert first_token != second_token
    with transaction() as db:
        rows = {row.token_hash: row for row in db.scalars(select(PasswordReset)).all()}
    assert set(rows) == {digest(first_token), digest(second_token)}
    # The first token is invalidated (marked used); only the second remains usable.
    assert rows[digest(first_token)].used_at is not None
    assert rows[digest(second_token)].used_at is None


def test_forgot_response_body_is_byte_identical_for_known_and_unknown(forgot_client, admin, monkeypatch):
    shared, mounted = forgot_client
    _create_user(shared, admin, "user@test.local")
    _capture_mailer(monkeypatch)
    known = mounted.post("/v1/auth/password/forgot", json={"email": "user@test.local"})
    unknown = mounted.post("/v1/auth/password/forgot", json={"email": "nobody@test.local"})
    assert known.status_code == unknown.status_code == 200
    assert known.content == unknown.content
