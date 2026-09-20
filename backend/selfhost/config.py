from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    ollama_url: str = "http://ollama:11434/v1"
    seed_local_whisper: bool = True
    seed_local_ollama: bool = True
    tts_url: str = "http://stt:8000"
    local_only: bool = True
    allow_private_http: bool = True
    audio_retention_days: int = 0  # 0 keeps original audio until explicit deletion
    job_lease_seconds: int = 900

    def validate_runtime(self):
        if len(self.secret_key.get_secret_value()) < 32:
            raise ValueError("OLLOMI_SECRET_KEY must contain at least 32 characters")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "files").mkdir(exist_ok=True)


@lru_cache
def settings() -> Settings:
    return Settings()
