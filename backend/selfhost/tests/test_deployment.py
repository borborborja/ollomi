import io
import importlib.util
import os
import stat
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[3]


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_environment_admin_seed_is_idempotent(client, monkeypatch):
    from selfhost.accounts import seed_admin_from_env
    from selfhost.db import User, transaction
    from selfhost.security import verify_password

    monkeypatch.setenv("OLLOMI_ADMIN_EMAIL", "Seed@Test.Local")
    monkeypatch.setenv("OLLOMI_ADMIN_PASSWORD", "initial-password-123")
    with transaction() as db:
        assert seed_admin_from_env(db) is True
    with transaction() as db:
        created = db.scalar(select(User).where(User.email == "seed@test.local"))
        assert created.admin is True
        original_hash = created.password_hash
        assert verify_password("initial-password-123", original_hash)

    monkeypatch.setenv("OLLOMI_ADMIN_PASSWORD", "replacement-password-456")
    with transaction() as db:
        assert seed_admin_from_env(db) is False
    with transaction() as db:
        unchanged = db.scalar(select(User).where(User.email == "seed@test.local"))
        assert unchanged.password_hash == original_hash
        assert not verify_password("replacement-password-456", unchanged.password_hash)


def test_environment_admin_seed_requires_both_values(client, monkeypatch):
    from selfhost.accounts import seed_admin_from_env
    from selfhost.db import transaction

    monkeypatch.setenv("OLLOMI_ADMIN_EMAIL", "seed@test.local")
    monkeypatch.delenv("OLLOMI_ADMIN_PASSWORD", raising=False)
    with transaction() as db, pytest.raises(ValueError, match="must be set together"):
        seed_admin_from_env(db)


def test_cli_supports_password_environment_and_stdin(client, monkeypatch):
    from selfhost.cli import main
    from selfhost.db import User, transaction
    from selfhost.security import verify_password

    monkeypatch.setenv("TEST_ADMIN_PASSWORD", "environment-password-123")
    main(
        [
            "create-admin",
            "--email",
            "env-admin@test.local",
            "--password-env",
            "TEST_ADMIN_PASSWORD",
        ]
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("standard-input-password-123\n"))
    main(
        [
            "create-admin",
            "--email",
            "stdin-admin@test.local",
            "--password-stdin",
        ]
    )

    with transaction() as db:
        env_admin = db.scalar(select(User).where(User.email == "env-admin@test.local"))
        stdin_admin = db.scalar(select(User).where(User.email == "stdin-admin@test.local"))
        assert env_admin.admin and verify_password("environment-password-123", env_admin.password_hash)
        assert stdin_admin.admin and verify_password("standard-input-password-123", stdin_admin.password_hash)


def test_environment_profiles_defer_transient_dns_failure(client, monkeypatch):
    from selfhost import profiles

    for key in list(os.environ):
        if any(key.startswith(f"OLLOMI_{purpose}") for purpose in ("STT", "CHAT", "EMBEDDING")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OLLOMI_CHAT1_PROVIDER", "custom")
    monkeypatch.setenv("OLLOMI_CHAT1_URL", "http://temporary-lan-name:11434/v1")
    monkeypatch.setenv("OLLOMI_CHAT1_MODEL", "qwen-test")

    def unresolved(*args, **kwargs):
        raise profiles.socket.gaierror("temporary DNS failure")

    monkeypatch.setattr(profiles.socket, "getaddrinfo", unresolved)
    configured = profiles.env_profiles()
    assert configured["chat"][0]["base_url"] == ("http://temporary-lan-name:11434/v1")
    with pytest.raises(HTTPException, match="cannot be resolved"):
        profiles.validate_url("http://temporary-lan-name:11434/v1")


def test_external_http_is_rejected_even_when_dns_is_deferred(client, monkeypatch):
    from selfhost.config import settings
    from selfhost.profiles import validate_url

    monkeypatch.setenv("OLLOMI_LOCAL_ONLY", "false")
    settings.cache_clear()
    with pytest.raises(HTTPException, match="require HTTPS"):
        validate_url(
            "http://external-provider.example/v1",
            external=True,
            allow_unresolved=True,
        )
    settings.cache_clear()


def test_disabling_local_ollama_seeds_only_whisper(client, monkeypatch):
    from selfhost.config import settings
    from selfhost.db import AIProfile, transaction
    from selfhost.profiles import seed_profiles

    monkeypatch.setenv("OLLOMI_SEED_LOCAL_OLLAMA", "false")
    settings.cache_clear()
    with transaction() as db:
        db.query(AIProfile).delete()
        seed_profiles(db)
    with transaction() as db:
        assert {row.purpose for row in db.query(AIProfile)} == {"stt"}
    settings.cache_clear()


def test_disabling_all_local_ai_seeds_no_profiles(client, monkeypatch):
    from selfhost.config import settings
    from selfhost.db import AIProfile, transaction
    from selfhost.profiles import seed_profiles

    monkeypatch.setenv("OLLOMI_SEED_LOCAL_WHISPER", "false")
    monkeypatch.setenv("OLLOMI_SEED_LOCAL_OLLAMA", "false")
    settings.cache_clear()
    with transaction() as db:
        db.query(AIProfile).delete()
        seed_profiles(db)
    with transaction() as db:
        assert db.query(AIProfile).count() == 0
    settings.cache_clear()


def test_initializer_selects_free_port_and_external_compose_chain(tmp_path, monkeypatch):
    selfhost_init = load_module("ollomi_selfhost_init", "scripts/selfhost_init.py")

    monkeypatch.setattr(selfhost_init, "port_available", lambda port: port == 8090)
    monkeypatch.setenv("BOOTSTRAP_PASSWORD", "bootstrap-password-123")
    args = selfhost_init.parser().parse_args(
        [
            "--external-ai",
            "--bind",
            "0.0.0.0",
            "--admin-email",
            "owner@test.local",
            "--admin-password-env",
            "BOOTSTRAP_PASSWORD",
        ]
    )
    destination, port = selfhost_init.initialize(tmp_path, args)
    content = destination.read_text()

    assert port == 8090
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert "COMPOSE_FILE=compose.yaml:deploy/compose.ghcr.yaml:" "deploy/compose.connected.yaml" in content
    assert "OLLOMI_IMAGE_OWNER=borborborja" in content
    assert f"OLLOMI_HOST_UID={os.getuid()}" in content
    assert "OLLOMI_BIND=0.0.0.0" in content
    assert "OLLOMI_PORT=8090" in content
    assert "OLLOMI_LOCAL_ONLY=false" in content
    assert "OLLOMI_SEED_LOCAL_WHISPER=false" in content
    assert "OLLOMI_SEED_LOCAL_OLLAMA=false" in content
    assert "COMPOSE_PROFILES=" not in content
    assert "\nOLLOMI_STT1_PROVIDER=whisper\n" not in content
    assert "# OLLOMI_STT1_PROVIDER=custom\n" in content
    assert "\nOLLOMI_CHAT1_PROVIDER=ollama\n" not in content
    assert "OLLOMI_ADMIN_EMAIL='owner@test.local'" in content
    assert "OLLOMI_ADMIN_PASSWORD='bootstrap-password-123'" in content


def test_initializer_defaults_to_ghcr_and_local_ollama(tmp_path, monkeypatch):
    selfhost_init = load_module("ollomi_selfhost_init", "scripts/selfhost_init.py")

    monkeypatch.setattr(selfhost_init, "port_available", lambda port: port == 8080)
    args = selfhost_init.parser().parse_args([])
    destination, port = selfhost_init.initialize(tmp_path, args)
    content = destination.read_text()

    assert port == 8080
    assert "COMPOSE_FILE=compose.yaml:deploy/compose.ghcr.yaml\n" in content
    assert "COMPOSE_PROFILES=local-whisper,local-ollama\n" in content
    assert "OLLOMI_SEED_LOCAL_WHISPER=true\n" in content
    assert "OLLOMI_SEED_LOCAL_OLLAMA=true\n" in content
    assert "\nOLLOMI_STT1_PROVIDER=whisper\n" in content
    assert "# OLLOMI_STT2_PROVIDER=custom\n" in content
    assert "\nOLLOMI_CHAT1_PROVIDER=ollama\n" in content
    assert "\nOLLOMI_EMBEDDING1_PROVIDER=ollama\n" in content


def test_initializer_rejects_an_occupied_requested_port(tmp_path, monkeypatch):
    selfhost_init = load_module("ollomi_selfhost_init", "scripts/selfhost_init.py")

    monkeypatch.setattr(selfhost_init, "port_available", lambda port: False)
    args = selfhost_init.parser().parse_args(["--port", "8080"])
    with pytest.raises(ValueError, match="already in use"):
        selfhost_init.initialize(tmp_path, args)


def test_model_downloader_uses_named_model_directory(tmp_path):
    destination = load_module("ollomi_download_models", "services/speech/download_models.py").destination

    assert destination(tmp_path, "large-v3") == Path(tmp_path) / "large-v3"
    with pytest.raises(ValueError, match="Unsupported Whisper model"):
        destination(tmp_path, "untrusted/path")
