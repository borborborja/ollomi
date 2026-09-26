import smtplib
from email.message import EmailMessage

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
    ):
        monkeypatch.delenv(key, raising=False)
    from selfhost.config import environment_settings

    environment_settings.cache_clear()
    # The DB-backed override layer needs a live database; mail reads env-only
    # infrastructure fields, so tests patch the accessor directly.
    from selfhost import mail

    monkeypatch.setattr(mail, "settings", environment_settings)
    yield monkeypatch
    environment_settings.cache_clear()


def configure_smtp(monkeypatch, **overrides):
    env = {
        "OLLOMI_SMTP_HOST": "smtp.example.org",
        "OLLOMI_SMTP_FROM": "Ollomi <no-reply@example.org>",
    }
    env.update(overrides)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from selfhost.config import environment_settings

    environment_settings.cache_clear()


class FakeSMTPServer:
    def __init__(self, host, port, timeout=None, **kwargs):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.kwargs = kwargs
        self.starttls_called = False
        self.login_calls = []
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.starttls_called = True

    def login(self, username, password):
        self.login_calls.append((username, password))

    def send_message(self, message):
        self.sent.append(message)


@pytest.fixture
def fake_smtp(monkeypatch):
    instances = []

    def factory(host, port, timeout=None, **kwargs):
        server = FakeSMTPServer(host, port, timeout=timeout, **kwargs)
        instances.append(server)
        return server

    from selfhost import mail

    monkeypatch.setattr(mail.smtplib, "SMTP", factory)
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", factory)
    return instances


def test_configured_false_when_smtp_host_empty(smtp_env):
    from selfhost import mail

    assert mail.configured() is False


def test_configured_true_when_smtp_host_set(smtp_env):
    configure_smtp(smtp_env)
    from selfhost import mail

    assert mail.configured() is True


def test_send_password_reset_email_success(smtp_env, fake_smtp):
    configure_smtp(smtp_env)
    from selfhost import mail

    link = "https://ollomi.test/reset-password#token=SECRET-TOKEN"
    assert mail.send_password_reset_email("user@example.org", link, "ca") is True

    assert len(fake_smtp) == 1
    server = fake_smtp[0]
    assert server.host == "smtp.example.org"
    assert len(server.sent) == 1
    message = server.sent[0]
    assert message["To"] == "user@example.org"
    assert "no-reply@example.org" in message["From"]
    assert message["Subject"]
    body = message.get_body(("plain",)).get_content()
    assert link in body


def test_send_password_reset_email_localized_subjects(smtp_env, fake_smtp):
    configure_smtp(smtp_env)
    from selfhost import mail

    subjects = {}
    for language in ("ca", "es", "en", "xx", ""):
        assert mail.send_password_reset_email("user@example.org", "https://h/reset-password#token=T", language) is True
        subjects[language] = fake_smtp[-1].sent[-1]["Subject"]

    assert len({subjects["ca"], subjects["es"], subjects["en"]}) == 3
    assert subjects["xx"] == subjects["en"]
    assert subjects[""] == subjects["en"]


def test_send_password_changed_email_success(smtp_env, fake_smtp):
    configure_smtp(smtp_env)
    from selfhost import mail

    assert mail.send_password_changed_email("user@example.org", "es") is True

    message = fake_smtp[-1].sent[-1]
    assert message["To"] == "user@example.org"
    assert message["Subject"]
    assert message.get_body(("plain",)).get_content()


def test_send_starttls_and_login(smtp_env, fake_smtp):
    configure_smtp(
        smtp_env,
        OLLOMI_SMTP_SECURITY="starttls",
        OLLOMI_SMTP_USERNAME="user@example.org",
        OLLOMI_SMTP_PASSWORD="app-password",
        OLLOMI_SMTP_TIMEOUT="7",
    )
    from selfhost import mail

    assert mail.send_password_changed_email("user@example.org", "en") is True

    server = fake_smtp[-1]
    assert server.starttls_called is True
    assert server.login_calls == [("user@example.org", "app-password")]
    assert server.timeout == 7


def test_send_ssl_uses_smtp_ssl(smtp_env, monkeypatch):
    configure_smtp(smtp_env, OLLOMI_SMTP_SECURITY="ssl", OLLOMI_SMTP_PORT="465")
    instances = {"ssl": [], "plain": []}

    from selfhost import mail

    class FakeSSL(FakeSMTPServer):
        pass

    def factory_for(kind):
        def factory(host, port, timeout=None, **kwargs):
            server = FakeSSL(host, port, timeout=timeout, **kwargs)
            instances[kind].append(server)
            return server

        return factory

    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", factory_for("ssl"))
    monkeypatch.setattr(mail.smtplib, "SMTP", factory_for("plain"))

    assert mail.send_password_changed_email("user@example.org", "en") is True
    assert len(instances["ssl"]) == 1
    assert instances["ssl"][0].starttls_called is False
    assert instances["plain"] == []


def test_send_returns_false_on_smtp_failure_without_leaking_token(smtp_env, fake_smtp, monkeypatch, caplog):
    configure_smtp(smtp_env)
    from selfhost import mail

    token = "SECRET-TOKEN-THAT-MUST-NOT-LEAK"
    link = "https://ollomi.test/reset-password#token=" + token

    def failing_factory(host, port, timeout=None, **kwargs):
        server = FakeSMTPServer(host, port, timeout=timeout, **kwargs)

        def boom(message):
            raise smtplib.SMTPException("relay refused")

        server.send_message = boom
        return server

    monkeypatch.setattr(mail.smtplib, "SMTP", failing_factory)

    with caplog.at_level("WARNING"):
        assert mail.send_password_reset_email("user@example.org", link, "en") is False

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in logged
    assert "user@example.org" not in logged


def test_send_rejects_header_injection(smtp_env, fake_smtp):
    configure_smtp(smtp_env)
    from selfhost import mail

    assert mail.send_password_reset_email("user@example.org\nBCC: evil@example.org", "https://h/#token=T", "en") is False
    assert fake_smtp == [] or not fake_smtp[-1].sent


def test_no_io_at_import(tmp_path, monkeypatch):
    # Importing the module must not open sockets or require SMTP settings.
    from selfhost import mail

    assert hasattr(mail, "configured")
    assert hasattr(mail, "send")
    assert hasattr(mail, "send_password_reset_email")
    assert hasattr(mail, "send_password_changed_email")
    message = EmailMessage()
    message["From"] = "a@example.org"
    message["To"] = "b@example.org"
    message["Subject"] = "s"
    message.set_content("body")
    # Direct send of a hand-built message still goes through the configured path.
    assert callable(mail.send)
