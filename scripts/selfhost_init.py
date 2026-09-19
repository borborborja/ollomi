#!/usr/bin/env python3
"""Generate local instance secrets once. Never overwrite an existing deployment."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
destination = root / ".env"
try:
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit(".env already exists; keeping all instance keys unchanged.")
with os.fdopen(descriptor, "w") as output:
    for key in ("OLLOMI_SECRET_KEY", "POSTGRES_PASSWORD", "TYPESENSE_API_KEY"):
        output.write(f"{key}={secrets.token_hex(32)}\n")
    output.write("OLLOMI_LOCAL_ONLY=true\nOLLOMI_BIND=127.0.0.1\nOLLOMI_PORT=8080\n")
    output.write(
        "OLLOMI_STT1_PROVIDER=whisper\n"
        "OLLOMI_STT1_MODEL=small\n"
        "OLLOMI_CHAT1_PROVIDER=ollama\n"
        "OLLOMI_CHAT1_MODEL=qwen3:4b\n"
        "OLLOMI_EMBEDDING1_PROVIDER=ollama\n"
        "OLLOMI_EMBEDDING1_MODEL=embeddinggemma\n"
    )
(root / "selfhost-data/models").mkdir(parents=True, exist_ok=True)
print("Created .env with private permissions and independent instance secrets.")
