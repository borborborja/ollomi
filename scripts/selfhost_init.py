#!/usr/bin/env python3
"""Create a safe, repeatable Compose configuration for one Ollomi instance."""

import argparse
import os
import secrets
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def port_available(port: int) -> bool:
    """Return whether a TCP port can be bound on all local interfaces."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def choose_port(requested: int | None = None) -> int:
    if requested is not None:
        if not 1 <= requested <= 65535:
            raise ValueError("--port must be between 1 and 65535")
        if not port_available(requested):
            raise ValueError(f"Port {requested} is already in use")
        return requested
    for candidate in (8080, 8090, *range(8081, 8090), *range(8091, 8101)):
        if port_available(candidate):
            return candidate
    raise RuntimeError("No free TCP port found between 8080 and 8100")


def compose_files(*, source_build: bool, connected: bool) -> str:
    files = ["compose.yaml"]
    if not source_build:
        files.append("deploy/compose.ghcr.yaml")
    if connected:
        files.append("deploy/compose.connected.yaml")
    return ":".join(files)


def dotenv_literal(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("Environment values cannot contain newlines")
    return "'" + value.replace("'", "\\'") + "'"


def initialize(root: Path, args: argparse.Namespace) -> tuple[Path, int]:
    destination = root / ".env"
    if destination.exists():
        raise FileExistsError(".env already exists; keeping all instance keys unchanged.")

    connected = args.connected or args.external_ai
    without_local_ollama = args.without_local_ollama or args.external_ai
    without_local_whisper = args.external_ai
    port = choose_port(args.port)

    admin_email = (args.admin_email or "").strip()
    admin_password = ""
    if bool(admin_email) != bool(args.admin_password_env):
        raise ValueError("--admin-email and --admin-password-env must be supplied together")
    if args.admin_password_env:
        if args.admin_password_env not in os.environ:
            raise ValueError(f"Environment variable {args.admin_password_env!r} is not set")
        admin_password = os.environ[args.admin_password_env]
        if len(admin_password) < 12:
            raise ValueError("Administrator password must contain at least 12 characters")

    lines = [
        f"COMPOSE_FILE={compose_files(source_build=args.source_build, connected=connected)}",
        "OLLOMI_IMAGE_OWNER=borborborja",
        f"OLLOMI_HOST_UID={os.getuid()}",
        f"OLLOMI_HOST_GID={os.getgid()}",
    ]
    compose_profiles = []
    if not without_local_whisper:
        compose_profiles.append("local-whisper")
    if not without_local_ollama:
        compose_profiles.append("local-ollama")
    if compose_profiles:
        lines.append(f"COMPOSE_PROFILES={','.join(compose_profiles)}")
    lines.extend(
        f"{key}={secrets.token_hex(32)}" for key in ("OLLOMI_SECRET_KEY", "POSTGRES_PASSWORD", "TYPESENSE_API_KEY")
    )
    external_stt_index = 1 if without_local_whisper else 2
    lines.extend(
        [
            f"OLLOMI_LOCAL_ONLY={'false' if connected else 'true'}",
            f"OLLOMI_BIND={args.bind}",
            f"OLLOMI_PORT={port}",
            f"OLLOMI_PUBLIC_URL=http://localhost:{port}",
            f"OLLOMI_SEED_LOCAL_WHISPER={'false' if without_local_whisper else 'true'}",
            f"OLLOMI_SEED_LOCAL_OLLAMA={'false' if without_local_ollama else 'true'}",
        ]
    )
    if not without_local_whisper:
        lines.extend(
            [
                "OLLOMI_STT1_PROVIDER=whisper",
                "OLLOMI_STT1_MODEL=small",
            ]
        )
    if not without_local_ollama:
        lines.extend(
            [
                "OLLOMI_CHAT1_PROVIDER=ollama",
                "OLLOMI_CHAT1_MODEL=qwen3:4b",
                "OLLOMI_EMBEDDING1_PROVIDER=ollama",
                "OLLOMI_EMBEDDING1_MODEL=embeddinggemma",
            ]
        )
    if admin_email:
        lines.extend(
            [
                f"OLLOMI_ADMIN_EMAIL={dotenv_literal(admin_email)}",
                f"OLLOMI_ADMIN_PASSWORD={dotenv_literal(admin_password)}",
            ]
        )

    lines.extend(
        [
            "",
            "# External/LAN OpenAI-compatible examples:",
            "# OLLOMI_CHAT1_PROVIDER=ollama",
            "# OLLOMI_CHAT1_URL=http://192.168.1.10:11434/v1",
            "# OLLOMI_CHAT1_MODEL=qwen3:8b",
            "# OLLOMI_CHAT1_API_KEY=ollama",
            "# OLLOMI_CHAT2_PROVIDER=openrouter",
            "# OLLOMI_CHAT2_URL=https://openrouter.ai/api/v1",
            "# OLLOMI_CHAT2_MODEL=openai/gpt-4.1-mini",
            "# OLLOMI_CHAT2_API_KEY=replace-me",
            f"# OLLOMI_STT{external_stt_index}_PROVIDER=custom",
            f"# OLLOMI_STT{external_stt_index}_URL=http://192.168.1.10:8000/v1",
            f"# OLLOMI_STT{external_stt_index}_MODEL=whisper-large-v3",
            f"# OLLOMI_STT{external_stt_index}_API_KEY=replace-me",
            "# OLLOMI_EMBEDDING1_PROVIDER=ollama",
            "# OLLOMI_EMBEDDING1_URL=http://192.168.1.10:11434/v1",
            "# OLLOMI_EMBEDDING1_MODEL=nomic-embed-text",
            "# OLLOMI_EMBEDDING1_API_KEY=ollama",
            "",
        ]
    )

    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write("\n".join(lines))
    (root / "selfhost-data/models").mkdir(parents=True, exist_ok=True)
    return destination, port


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--source-build",
        action="store_true",
        help="Build images locally instead of pulling the published GHCR images",
    )
    result.add_argument(
        "--connected",
        action="store_true",
        help="Allow external/LAN AI endpoints and include the connected Compose policy",
    )
    result.add_argument(
        "--without-local-ollama",
        action="store_true",
        help="Do not start or seed the local Ollama service",
    )
    result.add_argument(
        "--external-ai",
        action="store_true",
        help="Use only external/LAN STT, chat and embedding APIs; start no local AI service",
    )
    result.add_argument("--bind", default="127.0.0.1")
    result.add_argument("--port", type=int)
    result.add_argument("--admin-email")
    result.add_argument(
        "--admin-password-env",
        metavar="NAME",
        help="Read the optional initial admin password from this environment variable",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        destination, port = initialize(ROOT, args)
    except (FileExistsError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Created {destination} with private permissions; Ollomi will use port {port}.")
    if args.admin_email:
        print(
            "The initial admin will be created on startup. Remove OLLOMI_ADMIN_PASSWORD "
            "from .env after the first successful login."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
