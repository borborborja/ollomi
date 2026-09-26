import pytest


@pytest.fixture
def smtp_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLOMI_DATA_DIR", str(tmp_path / "data"))
    for key in (
        "OLLOMI_SMTP_HOST",
        "OLLOMI_SMTP_PORT",
        "OLLOMI_SMTP_SECURITY",
        "OLLOMI_SMTP_USERNAME",
        "OLLOMI_SMTP_PASSWORD",
        "OLLOMI_SMTP_FROM",
        "OLLOMI_SMTP_REPLY_TO",
        "OLLOMI_SMTP_TIMEOUT",
        "OLLOMI_PASSWORD_RESET_TTL_MINUTES",
    ):
        monkeypatch.delenv(key, raising=False)
    from selfhost.config import environment_settings

    environment_settings.cache_clear()
    yield monkeypatch
    environment_settings.cache_clear()


def _reload_settings():
    from selfhost.config import environment_settings

    environment_settings.cache_clear()
    return environment_settings()


def test_smtp_settings_valid_config_passes(smtp_env):
    smtp_env.setenv("OLLOMI_SMTP_HOST", "smtp.example.org")
    smtp_env.setenv("OLLOMI_SMTP_FROM", "Ollomi <no-reply@example.org>")
    smtp_env.setenv("OLLOMI_SMTP_PORT", "587")
    smtp_env.setenv("OLLOMI_SMTP_SECURITY", "starttls")
    smtp_env.setenv("OLLOMI_SMTP_USERNAME", "user@example.org")
    smtp_env.setenv("OLLOMI_SMTP_PASSWORD", "app-password")
    smtp_env.setenv("OLLOMI_SMTP_TIMEOUT", "10")
    smtp_env.setenv("OLLOMI_PASSWORD_RESET_TTL_MINUTES", "30")

    loaded = _reload_settings()
    loaded.validate_runtime()

    assert loaded.smtp_host == "smtp.example.org"
    assert loaded.smtp_port == 587
    assert loaded.smtp_security == "starttls"
    assert loaded.smtp_username == "user@example.org"
    assert loaded.smtp_password.get_secret_value() == "app-password"
    assert loaded.smtp_from == "Ollomi <no-reply@example.org>"
    assert loaded.smtp_timeout == 10
    assert loaded.password_reset_ttl_minutes == 30


def test_smtp_settings_host_without_from_raises(smtp_env):
    smtp_env.setenv("OLLOMI_SMTP_HOST", "smtp.example.org")

    loaded = _reload_settings()
    with pytest.raises(ValueError, match="OLLOMI_SMTP_FROM"):
        loaded.validate_runtime()


def test_smtp_settings_port_zero_raises(smtp_env):
    smtp_env.setenv("OLLOMI_SMTP_HOST", "smtp.example.org")
    smtp_env.setenv("OLLOMI_SMTP_FROM", "Ollomi <no-reply@example.org>")
    smtp_env.setenv("OLLOMI_SMTP_PORT", "0")

    loaded = _reload_settings()
    with pytest.raises(ValueError, match="OLLOMI_SMTP_PORT"):
        loaded.validate_runtime()


def test_smtp_settings_username_without_password_raises(smtp_env):
    smtp_env.setenv("OLLOMI_SMTP_HOST", "smtp.example.org")
    smtp_env.setenv("OLLOMI_SMTP_FROM", "Ollomi <no-reply@example.org>")
    smtp_env.setenv("OLLOMI_SMTP_USERNAME", "user@example.org")

    loaded = _reload_settings()
    with pytest.raises(ValueError, match="OLLOMI_SMTP_USERNAME and OLLOMI_SMTP_PASSWORD"):
        loaded.validate_runtime()


def test_smtp_settings_password_without_username_raises(smtp_env):
    smtp_env.setenv("OLLOMI_SMTP_HOST", "smtp.example.org")
    smtp_env.setenv("OLLOMI_SMTP_FROM", "Ollomi <no-reply@example.org>")
    smtp_env.setenv("OLLOMI_SMTP_PASSWORD", "app-password")

    loaded = _reload_settings()
    with pytest.raises(ValueError, match="OLLOMI_SMTP_USERNAME and OLLOMI_SMTP_PASSWORD"):
        loaded.validate_runtime()


def test_smtp_settings_timeout_out_of_range_raises(smtp_env):
    smtp_env.setenv("OLLOMI_SMTP_HOST", "smtp.example.org")
    smtp_env.setenv("OLLOMI_SMTP_FROM", "Ollomi <no-reply@example.org>")
    smtp_env.setenv("OLLOMI_SMTP_TIMEOUT", "0")

    loaded = _reload_settings()
    with pytest.raises(ValueError, match="OLLOMI_SMTP_TIMEOUT"):
        loaded.validate_runtime()


def test_smtp_settings_timeout_too_high_raises(smtp_env):
    smtp_env.setenv("OLLOMI_SMTP_HOST", "smtp.example.org")
    smtp_env.setenv("OLLOMI_SMTP_FROM", "Ollomi <no-reply@example.org>")
    smtp_env.setenv("OLLOMI_SMTP_TIMEOUT", "31")

    loaded = _reload_settings()
    with pytest.raises(ValueError, match="OLLOMI_SMTP_TIMEOUT"):
        loaded.validate_runtime()


def test_password_reset_ttl_minutes_zero_raises(smtp_env):
    smtp_env.setenv("OLLOMI_PASSWORD_RESET_TTL_MINUTES", "0")

    loaded = _reload_settings()
    with pytest.raises(ValueError, match="OLLOMI_PASSWORD_RESET_TTL_MINUTES"):
        loaded.validate_runtime()


def test_password_reset_ttl_minutes_too_high_raises(smtp_env):
    smtp_env.setenv("OLLOMI_PASSWORD_RESET_TTL_MINUTES", "1441")

    loaded = _reload_settings()
    with pytest.raises(ValueError, match="OLLOMI_PASSWORD_RESET_TTL_MINUTES"):
        loaded.validate_runtime()


def test_smtp_settings_defaults_are_safe(smtp_env):
    loaded = _reload_settings()
    loaded.validate_runtime()

    assert loaded.smtp_host == ""
    assert loaded.smtp_port == 587
    assert loaded.smtp_security == "starttls"
    assert loaded.smtp_username == ""
    assert loaded.smtp_password.get_secret_value() == ""
    assert loaded.smtp_from == ""
    assert loaded.smtp_reply_to == ""
    assert loaded.smtp_timeout == 10
    assert loaded.password_reset_ttl_minutes == 30


def test_smtp_settings_are_infrastructure_only():
    from selfhost.config import INFRASTRUCTURE_FIELDS

    for field in (
        "smtp_host",
        "smtp_port",
        "smtp_security",
        "smtp_username",
        "smtp_password",
        "smtp_from",
        "smtp_reply_to",
        "smtp_timeout",
    ):
        assert field in INFRASTRUCTURE_FIELDS
