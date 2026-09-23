import io
import importlib.util
import os
import stat
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

ROOT = Path(__file__).resolve().parents[3]


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_environment_admin_seed_applies_password_changes(client, monkeypatch):
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
        assert seed_admin_from_env(db) is True
    with transaction() as db:
        changed = db.scalar(select(User).where(User.email == "seed@test.local"))
        assert changed.password_hash != original_hash
        assert verify_password("replacement-password-456", changed.password_hash)
        assert seed_admin_from_env(db) is False


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


def test_cli_rebuilds_only_derived_search_data(client, monkeypatch, capsys):
    from selfhost import cli
    from selfhost.config import settings
    from selfhost.db import AIProfile, Job, Record, User, transaction

    monkeypatch.setenv("OLLOMI_ALLOW_USER_MODEL_SELECTION", "true")
    settings.cache_clear()

    with transaction() as db:
        # `embeddings` is intentionally migration-managed (pgvector), rather
        # than an ORM model.  The SQLite fixture builds metadata only.
        db.execute(text("CREATE TABLE embeddings (record_id TEXT)"))
        user = db.scalar(select(User).where(User.email == "admin@test.local"))
        db.add(
            AIProfile(
                id="test-embedding",
                name="Test embedding",
                purpose="embedding",
                base_url="http://127.0.0.1:11434/v1",
                model="test-model",
                capabilities={"provider": "custom"},
            )
        )
        user.preferences = {"ai_profiles": {"embedding": "test-embedding"}}
        db.add(Record(user_id=user.id, kind="memory", data={"content": "restored memory"}))
    purged = []
    monkeypatch.setattr(cli, "purge_all_text_index", lambda: purged.append(True))

    cli.main(["rebuild-search-index"])

    with transaction() as db:
        jobs = list(db.scalars(select(Job).where(Job.kind == "reindex")))
        assert len(jobs) == 1
        assert jobs[0].payload["embedding"]["id"] == "test-embedding"
    assert purged == [True]
    assert "queued rebuild for 1 enabled user" in capsys.readouterr().out


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


def test_copyable_env_example_targets_external_or_lan_models_without_local_ai():
    content = (ROOT / ".env.example").read_text()
    compose = (ROOT / "compose.yaml").read_text()

    assert 'env_file: ["${OLLOMI_ENV_FILE:-.env}"]' in compose
    assert "COMPOSE_FILE=compose.yaml:deploy/compose.connected.yaml" in content
    assert "OLLOMI_LOCAL_ONLY=false" in content
    assert "OLLOMI_SEED_LOCAL_WHISPER=false" in content
    assert "OLLOMI_SEED_LOCAL_OLLAMA=false" in content
    assert "OLLOMI_MCP_ENABLED=false" in content
    assert "OLLOMI_STT1_PROVIDER=custom" in content
    assert "OLLOMI_CHAT1_PROVIDER=ollama" in content
    assert "OLLOMI_EMBEDDING1_PROVIDER=ollama" in content
    assert "OLLOMI_ADMIN_PASSWORD=CHANGE_ME_A_LONG_UNIQUE_PASSWORD" in content
    assert "OLLOMI_STT1_PROVIDER=whisper" not in content
    assert "OLLOMI_CHAT1_MODEL=qwen3:4b" not in content


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
    assert "COMPOSE_FILE=compose.yaml:deploy/compose.connected.yaml" in content
    assert "OLLOMI_IMAGE_OWNER=" not in content
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


def test_initializer_defaults_to_source_build_and_local_ollama(tmp_path, monkeypatch):
    selfhost_init = load_module("ollomi_selfhost_init", "scripts/selfhost_init.py")

    monkeypatch.setattr(selfhost_init, "port_available", lambda port: port == 8080)
    args = selfhost_init.parser().parse_args([])
    destination, port = selfhost_init.initialize(tmp_path, args)
    content = destination.read_text()

    assert port == 8080
    assert "COMPOSE_FILE=compose.yaml\n" in content
    assert "OLLOMI_IMAGE_OWNER=" not in content
    assert "COMPOSE_PROFILES=local-whisper,local-ollama\n" in content
    assert "OLLOMI_SEED_LOCAL_WHISPER=true\n" in content
    assert "OLLOMI_SEED_LOCAL_OLLAMA=true\n" in content
    assert "\nOLLOMI_STT1_PROVIDER=whisper\n" in content
    assert "# OLLOMI_STT2_PROVIDER=custom\n" in content
    assert "\nOLLOMI_CHAT1_PROVIDER=ollama\n" in content
    assert "\nOLLOMI_EMBEDDING1_PROVIDER=ollama\n" in content


def test_initializer_adds_self_contained_tls_profile_for_a_public_domain(tmp_path, monkeypatch):
    selfhost_init = load_module("ollomi_selfhost_init", "scripts/selfhost_init.py")

    monkeypatch.setattr(selfhost_init, "port_available", lambda port: port == 8080)
    args = selfhost_init.parser().parse_args(["--tls-domain", "Ollomi.Example.Com."])
    destination, _port = selfhost_init.initialize(tmp_path, args)
    content = destination.read_text()

    assert "COMPOSE_FILE=compose.yaml:deploy/compose.tls.yaml" in content
    assert "COMPOSE_PROFILES=local-whisper,local-ollama,public-tls" in content
    assert "OLLOMI_PUBLIC_URL=https://ollomi.example.com" in content
    assert "OLLOMI_TLS_DOMAIN=ollomi.example.com" in content
    assert "OLLOMI_TLS_BIND=0.0.0.0" in content
    assert "OLLOMI_HTTP_PORT=80" in content
    assert "OLLOMI_HTTPS_PORT=443" in content
    assert "OLLOMI_MCP_PUBLIC_URL=https://ollomi.example.com" in content


@pytest.mark.parametrize(
    "value",
    [
        "https://ollomi.example.com",
        "ollomi.example.com:443",
        "localhost",
        "127.0.0.1",
        "bad_domain.example",
        "-bad.example",
    ],
)
def test_initializer_rejects_non_dns_tls_domain(value):
    selfhost_init = load_module("ollomi_selfhost_init", "scripts/selfhost_init.py")

    with pytest.raises(ValueError, match="--tls-domain"):
        selfhost_init.normalize_tls_domain(value)


def test_initializer_uses_only_explicit_published_image_coordinates(tmp_path, monkeypatch):
    selfhost_init = load_module("ollomi_selfhost_init", "scripts/selfhost_init.py")

    monkeypatch.setattr(selfhost_init, "port_available", lambda port: port == 8080)
    args = selfhost_init.parser().parse_args(
        ["--published-images", "--image-owner", "example-owner", "--image-tag", "v1.0.0"]
    )
    destination, _port = selfhost_init.initialize(tmp_path, args)
    content = destination.read_text()

    assert "COMPOSE_FILE=compose.yaml:deploy/compose.ghcr.yaml\n" in content
    assert "OLLOMI_IMAGE_OWNER=example-owner\n" in content
    assert "OLLOMI_IMAGE_TAG=v1.0.0\n" in content


def test_initializer_cli_rejects_ambiguous_published_images(tmp_path, monkeypatch):
    selfhost_init = load_module("ollomi_selfhost_init", "scripts/selfhost_init.py")

    monkeypatch.setattr(selfhost_init, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="--published-images requires --image-owner and --image-tag"):
        selfhost_init.main(["--published-images"])
    assert not (tmp_path / ".env").exists()


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


def test_voiceprint_image_bakes_verified_weights_and_disables_runtime_downloads():
    dockerfile = (ROOT / "services/voiceprint/Dockerfile").read_text()
    application = (ROOT / "services/voiceprint/app.py").read_text()
    published_compose = (ROOT / "deploy/examples/voiceprint/compose.ghcr.yaml").read_text()

    assert "VOICEPRINT_MODEL_REVISION=0f99f2d0ebe89ac095bcc5903c4dd8f72b367286" in dockerfile
    assert "VOICEPRINT_CLASSIFIER_SHA256=fd9e3634fe68bd0a427c95e354c0c677374f62b3f434e45b78599950d860d535" in dockerfile
    assert "VOICEPRINT_EMBEDDING_SHA256=0575cb64845e6b9a10db9bcb74d5ac32b326b8dc90352671d345e2ee3d0126a2" in dockerfile
    assert "VOICEPRINT_NORMALIZATION_SHA256=cd70225b05b37be64fc5a95e24395d804231d43f74b2e1e5a513db7b69b34c33" in dockerfile
    assert "snapshot_download" in dockerfile
    assert "sha256sum --check --strict" in dockerfile
    assert "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1" in dockerfile
    assert "pretrained_path: /opt/ollomi-voiceprint-model" in dockerfile
    assert 'os.getenv("VOICEPRINT_MODEL", "/opt/ollomi-voiceprint-model")' in application
    assert "ghcr.io/${OLLOMI_IMAGE_OWNER" in published_compose
    assert "ollomi-voiceprint:${OLLOMI_IMAGE_TAG" in published_compose
