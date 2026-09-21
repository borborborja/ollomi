#!/usr/bin/env python3
"""Create a safe, repeatable Compose configuration for one Ollomi instance."""

import argparse
import ipaddress
import os
import secrets
import socket
from pathlib import Path
from urllib.parse import urlsplit

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


def compose_files(*, source_build: bool, connected: bool, tls: bool) -> str:
    files = ["compose.yaml"]
    if not source_build:
        files.append("deploy/compose.ghcr.yaml")
    if connected:
        files.append("deploy/compose.connected.yaml")
    if tls:
        files.append("deploy/compose.tls.yaml")
    return ":".join(files)


def dotenv_literal(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("Environment values cannot contain newlines")
    return "'" + value.replace("'", "\\'") + "'"


def normalize_tls_domain(value: str) -> str:
    """Accept exactly one public DNS name, never a URL, path or credentials."""
    candidate = value.strip().lower().rstrip(".")
    try:
        parsed = urlsplit("//" + candidate)
        port = parsed.port
        ipaddress.ip_address(candidate)
        is_ip_address = True
    except ValueError:
        is_ip_address = False
    try:
        parsed = urlsplit("//" + candidate)
        port = parsed.port
    except ValueError:
        raise ValueError("--tls-domain must be one public DNS name, without a scheme, path or port") from None
    if (
        not candidate
        or not candidate.isascii()
        or is_ip_address
        or "://" in candidate
        or parsed.hostname != candidate
        or port is not None
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or "." not in candidate
        or any(
            part == ""
            or len(part) > 63
            or part.startswith("-")
            or part.endswith("-")
            or not part.replace("-", "").isalnum()
            for part in candidate.split(".")
        )
    ):
        raise ValueError("--tls-domain must be one public DNS name, without a scheme, path or port")
    return candidate


def initialize(root: Path, args: argparse.Namespace) -> tuple[Path, int]:
    destination = root / ".env"
    if destination.exists():
        raise FileExistsError(".env already exists; keeping all instance keys unchanged.")

    connected = args.connected or args.external_ai
    without_local_ollama = args.without_local_ollama or args.external_ai
    without_local_whisper = args.external_ai
    port = choose_port(args.port)
    tls_domain = normalize_tls_domain(args.tls_domain) if args.tls_domain else None

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
        f"COMPOSE_FILE={compose_files(source_build=args.source_build, connected=connected, tls=bool(tls_domain))}",
        f"OLLOMI_HOST_UID={os.getuid()}",
        f"OLLOMI_HOST_GID={os.getgid()}",
    ]
    if not args.source_build:
        lines.extend(
            [
                f"OLLOMI_IMAGE_OWNER={args.image_owner}",
                f"OLLOMI_IMAGE_TAG={args.image_tag}",
            ]
        )
    compose_profiles = []
    if not without_local_whisper:
        compose_profiles.append("local-whisper")
    if not without_local_ollama:
        compose_profiles.append("local-ollama")
    if tls_domain:
        compose_profiles.append("public-tls")
    if compose_profiles:
        lines.append(f"COMPOSE_PROFILES={','.join(compose_profiles)}")
    lines.extend(
        f"{key}={secrets.token_hex(32)}" for key in ("OLLOMI_SECRET_KEY", "POSTGRES_PASSWORD", "TYPESENSE_API_KEY")
    )
    external_stt_index = 1 if without_local_whisper else 2
    external_embedding_index = 1 if without_local_ollama else 2
    lines.extend(
        [
            f"OLLOMI_LOCAL_ONLY={'false' if connected else 'true'}",
            f"OLLOMI_BIND={args.bind}",
            f"OLLOMI_PORT={port}",
            f"OLLOMI_PUBLIC_URL={'https://' + tls_domain if tls_domain else 'http://localhost:' + str(port)}",
            f"OLLOMI_SEED_LOCAL_WHISPER={'false' if without_local_whisper else 'true'}",
            f"OLLOMI_SEED_LOCAL_OLLAMA={'false' if without_local_ollama else 'true'}",
            "# Let users choose a configured model; false keeps the first configured model as primary.",
            "OLLOMI_ALLOW_USER_MODEL_SELECTION=false",
            "# Set MCP_ENABLED=true only with a stable public HTTPS URL.",
            "OLLOMI_MCP_ENABLED=false",
            "# OLLOMI_MCP_PUBLIC_URL=https://ollomi.example.com",
            "# Optional remote CPU voiceprint service; see deploy/examples/voiceprint/README.md",
            "# OLLOMI_VOICEPRINT_URL=https://voiceprint.example.internal",
            "# OLLOMI_VOICEPRINT_API_KEY=replace-with-the-same-service-key",
            "# OLLOMI_VOICEPRINT_THRESHOLD=0.72",
        ]
    )
    if tls_domain:
        lines.extend(
            [
                f"OLLOMI_TLS_DOMAIN={tls_domain}",
                "OLLOMI_TLS_BIND=0.0.0.0",
                "OLLOMI_HTTP_PORT=80",
                "OLLOMI_HTTPS_PORT=443",
                f"OLLOMI_MCP_PUBLIC_URL=https://{tls_domain}",
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
            "# Native STT alternatives (use consecutive numbered entries for fallback):",
            f"# OLLOMI_STT{external_stt_index}_PROVIDER=gemini",
            f"# OLLOMI_STT{external_stt_index}_MODEL=gemini-3.5-transcribe",
            f"# OLLOMI_STT{external_stt_index}_API_KEY=replace-me",
            f"# OLLOMI_STT{external_stt_index + 1}_PROVIDER=assemblyai",
            f"# OLLOMI_STT{external_stt_index + 1}_MODEL=universal-3-5-pro",
            f"# OLLOMI_STT{external_stt_index + 1}_API_KEY=replace-me",
            f"# OLLOMI_STT{external_stt_index + 2}_PROVIDER=deepgram",
            f"# OLLOMI_STT{external_stt_index + 2}_MODEL=nova-3",
            f"# OLLOMI_STT{external_stt_index + 2}_API_KEY=replace-me",
            "# OLLOMI_EMBEDDING1_PROVIDER=ollama",
            "# OLLOMI_EMBEDDING1_URL=http://192.168.1.10:11434/v1",
            "# OLLOMI_EMBEDDING1_MODEL=nomic-embed-text",
            "# OLLOMI_EMBEDDING1_API_KEY=ollama",
            "# Native embedding alternatives (match dimensions across all fallbacks):",
            f"# OLLOMI_EMBEDDING{external_embedding_index}_PROVIDER=voyage",
            f"# OLLOMI_EMBEDDING{external_embedding_index}_MODEL=voyage-4-lite",
            f"# OLLOMI_EMBEDDING{external_embedding_index}_API_KEY=replace-me",
            f"# OLLOMI_EMBEDDING{external_embedding_index}_DIMENSIONS=1024",
            f"# OLLOMI_EMBEDDING{external_embedding_index + 1}_PROVIDER=cohere",
            f"# OLLOMI_EMBEDDING{external_embedding_index + 1}_MODEL=embed-v4.0",
            f"# OLLOMI_EMBEDDING{external_embedding_index + 1}_API_KEY=replace-me",
            f"# OLLOMI_EMBEDDING{external_embedding_index + 1}_DIMENSIONS=1024",
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
    result.set_defaults(source_build=True)
    result.add_argument(
        "--source-build",
        action="store_true",
        dest="source_build",
        help="Build images locally (the default until a reviewed release has been published)",
    )
    result.add_argument(
        "--published-images",
        action="store_false",
        dest="source_build",
        help="Pull reviewed images from GHCR instead of building this checkout",
    )
    result.add_argument(
        "--image-owner",
        help="GitHub owner that published this Ollomi fork; required with --published-images",
    )
    result.add_argument(
        "--image-tag",
        help="Reviewed Ollomi release tag; required with --published-images",
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
    result.add_argument(
        "--tls-domain",
        help="Public DNS name for Caddy-managed HTTPS (requires inbound ports 80 and 443)",
    )
    result.add_argument("--admin-email")
    result.add_argument(
        "--admin-password-env",
        metavar="NAME",
        help="Read the optional initial admin password from this environment variable",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.source_build and (not args.image_owner or not args.image_tag):
        raise SystemExit("--published-images requires --image-owner and --image-tag")
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
