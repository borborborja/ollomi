import base64
import hashlib
import json
import logging
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import SecretStr, TypeAdapter
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

# Infrastructure credentials and paths are controlled by Compose, never by a
# running web process. Every other Settings field can be overridden in the DB.
INFRASTRUCTURE_FIELDS = {
    "database_url",
    "redis_url",
    "data_dir",
    "secret_key",
    "typesense_url",
    "typesense_key",
    "smtp_host",
    "smtp_port",
    "smtp_security",
    "smtp_username",
    "smtp_password",
    "smtp_from",
    "smtp_reply_to",
    "smtp_timeout",
}
RESTART_FIELDS = {"seed_local_whisper", "seed_local_ollama", "stt_url", "ollama_url"}
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OLLOMI_", env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://ollomi:ollomi@postgres/ollomi"
    redis_url: str = "redis://redis:6379/0"
    data_dir: Path = Path("/data")
    secret_key: SecretStr
    public_url: str = "http://localhost:8080"
    access_minutes: int = 15
    refresh_days: int = 30
    max_upload_mb: int = 1024
    max_audio_seconds: int = 43200
    typesense_url: str = "http://typesense:8108"
    typesense_key: SecretStr = SecretStr("")
    stt_url: str = "http://stt:8000/v1"
    # Windows at or below this RMS (16-bit PCM) are treated as silence when
    # deciding whether an STT segment is a Whisper-style silence artefact.
    stt_silence_rms: int = 60
    ollama_url: str = "http://ollama:11434/v1"
    seed_local_whisper: bool = True
    seed_local_ollama: bool = True
    # Environment profiles remain the administrator's policy unless this is
    # explicitly enabled. The API enforces this; the mobile control is only a
    # presentation of the same policy.
    allow_user_model_selection: bool = False
    tts_url: str = "http://stt:8000"
    local_only: bool = True
    allow_private_http: bool = True
    audio_retention_days: int = 0  # 0 keeps original audio until explicit deletion
    job_lease_seconds: int = 900
    # Media/enrichment jobs are retried by `recover` up to this many attempts
    # before their conversation is marked failed instead of staying processing.
    job_retry_attempts: int = 3
    mcp_enabled: bool = False
    mcp_public_url: str = ""
    mcp_access_minutes: int = 15
    mcp_refresh_days: int = 30
    # A speaker embedding service deliberately lives outside the main stack:
    # ECAPA is CPU-heavy and many deployments run it on a separate host.
    # An empty URL disables voiceprint enrollment/recognition entirely.
    voiceprint_url: str = ""
    voiceprint_api_key: SecretStr = SecretStr("")
    voiceprint_threshold: float = 0.72
    # The public OSM endpoint needs no key. A local OSM tile server can replace
    # it without changing the Android app.
    map_tile_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    # Outbound mail for password recovery. Empty smtp_host disables email
    # delivery entirely (forgot-password returns 503). These are env-only so
    # a web admin can never silently reroute or capture reset links.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    smtp_reply_to: str = ""
    smtp_timeout: int = 10
    # One-use password-reset tokens expire after this many minutes.
    password_reset_ttl_minutes: int = 30

    def validate_runtime(self):
        if len(self.secret_key.get_secret_value()) < 32:
            raise ValueError("OLLOMI_SECRET_KEY must contain at least 32 characters")
        if not 0 <= self.stt_silence_rms <= 32768:
            raise ValueError("OLLOMI_STT_SILENCE_RMS must be between 0 and 32768")
        if not 1 <= self.job_retry_attempts <= 10:
            raise ValueError("OLLOMI_JOB_RETRY_ATTEMPTS must be between 1 and 10")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "files").mkdir(exist_ok=True)
        if self.mcp_enabled:
            parsed = urlsplit(self.mcp_public_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "OLLOMI_MCP_PUBLIC_URL must be an absolute HTTPS URL without credentials, query or fragment"
                )
            if not 1 <= self.mcp_access_minutes <= 60:
                raise ValueError("OLLOMI_MCP_ACCESS_MINUTES must be between 1 and 60")
            if not 1 <= self.mcp_refresh_days <= 365:
                raise ValueError("OLLOMI_MCP_REFRESH_DAYS must be between 1 and 365")
        if self.voiceprint_url:
            parsed = urlsplit(self.voiceprint_url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "OLLOMI_VOICEPRINT_URL must be an absolute HTTP(S) URL without credentials, query or fragment"
                )
            if not 0.5 <= self.voiceprint_threshold <= 0.95:
                raise ValueError("OLLOMI_VOICEPRINT_THRESHOLD must be between 0.5 and 0.95")
        try:
            sample = self.map_tile_url.format(z=1, x=1, y=1)
        except (KeyError, ValueError, IndexError):
            raise ValueError("OLLOMI_MAP_TILE_URL must contain {z}, {x} and {y}") from None
        parsed = urlsplit(sample)
        if (
            any(token not in self.map_tile_url for token in ("{z}", "{x}", "{y}"))
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("OLLOMI_MAP_TILE_URL must be an HTTP(S) tile URL without credentials or query")
        if self.smtp_host:
            if not self.smtp_from:
                raise ValueError("OLLOMI_SMTP_FROM must be set when OLLOMI_SMTP_HOST is configured")
            if not 1 <= self.smtp_port <= 65535:
                raise ValueError("OLLOMI_SMTP_PORT must be between 1 and 65535")
            if not 1 <= self.smtp_timeout <= 30:
                raise ValueError("OLLOMI_SMTP_TIMEOUT must be between 1 and 30")
            has_username = bool(self.smtp_username)
            has_password = bool(self.smtp_password.get_secret_value())
            if has_username != has_password:
                raise ValueError("OLLOMI_SMTP_USERNAME and OLLOMI_SMTP_PASSWORD must be set together")
        if not 5 <= self.password_reset_ttl_minutes <= 1440:
            raise ValueError("OLLOMI_PASSWORD_RESET_TTL_MINUTES must be between 5 and 1440")


@lru_cache
def environment_settings() -> Settings:
    return Settings()


@lru_cache
def _override_engine(url: str):
    return create_engine(url, pool_pre_ping=True)


def _cipher(base: Settings):
    key = hashlib.sha256(base.secret_key.get_secret_value().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encode_override(base: Settings, value):
    return _cipher(base).encrypt(json.dumps(value).encode()).decode()


def decode_override(base: Settings, value):
    return json.loads(_cipher(base).decrypt(value.encode()))


def environment_locked(field: str) -> bool:
    return "OLLOMI_" + field.upper() in os.environ


@lru_cache(maxsize=2)
def _effective_settings(epoch: int) -> Settings:
    base = environment_settings()
    try:
        with _override_engine(base.database_url).connect() as connection:
            rows = connection.execute(text("SELECT key, value FROM instance WHERE key LIKE 'setting:%'")).all()
    except (OperationalError, ProgrammingError) as error:
        # Configuration can be inspected before migrations or while the DB is
        # unavailable. Requests needing durable state fail at their own DB call.
        logger.warning("Runtime settings store unavailable: %s", type(error).__name__)
        rows = []
    values = {}
    for key, encrypted in rows:
        field = key.removeprefix("setting:")
        if field in Settings.model_fields and field not in INFRASTRUCTURE_FIELDS and not environment_locked(field):
            values[field] = TypeAdapter(Settings.model_fields[field].annotation).validate_python(
                decode_override(base, encrypted)
            )
    return base.model_copy(update=values)


def settings() -> Settings:
    # A short cache makes web edits visible to workers and other API processes.
    return _effective_settings(int(time.monotonic() // 3))


def clear_settings_cache():
    environment_settings.cache_clear()
    _effective_settings.cache_clear()
    _override_engine.cache_clear()


settings.cache_clear = clear_settings_cache
