import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("OLLOMI_SECRET_KEY", "unit-test-instance-secret-not-for-deployment")

from selfhost.accounts import normalize_email, validate_password
from selfhost.db import (
    Base,
    McpApiKey,
    McpOauthClient,
    McpOauthToken,
    Session,
    User,
    engine,
    now,
    transaction,
)
from selfhost.security import passwords, revoke_credentials


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLOMI_DATABASE_URL", "sqlite:///" + str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("OLLOMI_DATA_DIR", str(tmp_path / "data"))
    from selfhost.config import settings

    settings.cache_clear()
    engine.cache_clear()
    Base.metadata.create_all(engine())
    with transaction() as db:
        yield db
    engine().dispose()
    engine.cache_clear()
    settings.cache_clear()


def _make_user(db, email="user@test.local", password="user-password-123"):
    user = User(
        email=normalize_email(email),
        name=email.split("@", 1)[0],
        password_hash=passwords.hash(password),
        admin=False,
    )
    db.add(user)
    db.flush()
    return user


def _make_session(db, user):
    session = Session(user_id=user.id, refresh_hash="hash-" + user.id, expires_at=now() + timedelta(days=1))
    db.add(session)
    db.flush()
    return session


def _make_mcp_api_key(db, user):
    key = McpApiKey(
        user_id=user.id,
        name="test-key",
        token_hash="keyhash-" + user.id,
        key_prefix="prefix",
    )
    db.add(key)
    db.flush()
    return key


def _make_mcp_oauth_token(db, user):
    client = McpOauthClient(
        client_id="client-" + user.id,
        name="test-client",
        redirect_uri="https://example.org/callback",
    )
    db.add(client)
    db.flush()
    token = McpOauthToken(
        client_id=client.id,
        user_id=user.id,
        token_hash="tokenhash-" + user.id,
        token_type="access",
        scopes=[],
        expires_at=now() + timedelta(days=1),
    )
    db.add(token)
    db.flush()
    return token


def test_revoke_credentials_revokes_sessions_and_mcp(db_session):
    user = _make_user(db_session)
    session = _make_session(db_session, user)
    api_key = _make_mcp_api_key(db_session, user)
    oauth_token = _make_mcp_oauth_token(db_session, user)

    revoke_credentials(db_session, user.id)
    db_session.flush()

    assert session.revoked is True
    assert api_key.revoked is True
    assert oauth_token.revoked is True


def test_revoke_credentials_keep_session_id_preserves_exactly_one(db_session):
    user = _make_user(db_session)
    keep = _make_session(db_session, user)
    keep.refresh_hash = "keep-hash"
    other = Session(user_id=user.id, refresh_hash="other-hash", expires_at=now() + timedelta(days=1))
    db_session.add(other)
    db_session.flush()

    revoke_credentials(db_session, user.id, keep_session_id=keep.id)
    db_session.flush()

    assert keep.revoked is False
    assert other.revoked is True


def test_cli_reset_password_revokes_mcp_api_key(db_session, monkeypatch):
    from selfhost.cli import main

    user = _make_user(db_session)
    session = _make_session(db_session, user)
    api_key = _make_mcp_api_key(db_session, user)
    oauth_token = _make_mcp_oauth_token(db_session, user)
    session_id = session.id
    api_key_id = api_key.id
    oauth_token_id = oauth_token.id
    db_session.commit()

    monkeypatch.setattr(
        "sys.argv",
        ["ollomi", "reset-password", "--email", user.email, "--password-env", "TEST_PW"],
    )
    monkeypatch.setenv("TEST_PW", "new-password-123")
    main()

    with transaction() as db:
        assert db.get(Session, session_id).revoked is True
        assert db.get(McpApiKey, api_key_id).revoked is True
        assert db.get(McpOauthToken, oauth_token_id).revoked is True
