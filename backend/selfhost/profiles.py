import ipaddress
import json
import logging
import os
import socket
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from selfhost.config import settings
from selfhost.db import AIProfile, User, transaction
from selfhost.observability import record_fallback
from selfhost.security import seal, unseal

PURPOSES = ("stt", "chat", "embedding")
PROVIDER_DEFAULTS = {
    "openai": ("https://api.openai.com/v1", True),
    "openrouter": ("https://openrouter.ai/api/v1", True),
    "ollama-cloud": ("https://ollama.com/v1", True),
    "ollama_cloud": ("https://ollama.com/v1", True),
    "ollama": (None, False),
    "whisper": (None, False),
    "custom": (None, False),
}
logger = logging.getLogger(__name__)


def validate_url(value: str, external: bool = False, allow_unresolved: bool = False):
    url = urlsplit(value)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise HTTPException(422, "Use an HTTP(S) base URL without credentials, query or fragment")
    if external and settings().local_only:
        raise HTTPException(422, "External providers require OLLOMI_LOCAL_ONLY=false")
    if external and url.scheme != "https":
        raise HTTPException(422, "External providers require HTTPS")
    try:
        addresses = {ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(url.hostname, url.port or 443)}
    except socket.gaierror:
        if allow_unresolved:
            logger.warning(
                "An inference hostname did not resolve during configuration seed; "
                "it will be checked again before use"
            )
            return value.rstrip("/")
        raise HTTPException(422, "Server hostname cannot be resolved") from None
    for address in addresses:
        if address.is_link_local or address.is_multicast or address.is_unspecified:
            raise HTTPException(422, "This network address is not allowed")
        if not external and not (address.is_private or address.is_loopback):
            raise HTTPException(422, "Public servers must be explicitly marked external")
    return value.rstrip("/")


def public_profile(row, admin=False):
    runtime = (row.capabilities or {}).get("runtime", {})
    result = {
        "id": row.id,
        "name": row.name,
        "purpose": row.purpose,
        "model": row.model,
        "enabled": row.enabled,
        "external": row.external,
        "capabilities": row.capabilities,
        "revision": row.revision,
        "managed_by": (row.capabilities or {}).get("managed_by", "app"),
        "priority": (row.capabilities or {}).get("priority"),
        "provider": (row.capabilities or {}).get("provider", "custom"),
        "status": runtime.get("status", "unknown"),
        "last_checked_at": runtime.get("last_checked_at"),
        "last_success_at": runtime.get("last_success_at"),
    }
    if admin:
        result.update(base_url=row.base_url, has_api_key=bool(row.encrypted_key))
    return result


def snapshot(row):
    return {
        "id": row.id,
        "base_url": row.base_url,
        "model": row.model,
        "encrypted_key": row.encrypted_key,
        "external": row.external,
        "revision": row.revision,
        "purpose": row.purpose,
        "capabilities": row.capabilities,
        "name": row.name,
    }


def _env_bool(value, default=False):
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError(f"Invalid boolean value: {value}")
    return normalized in {"true", "1", "yes"}


def env_profiles():
    """Read ordered provider chains from OLLOMI_<PURPOSE><N>_* variables."""
    configured = {purpose: [] for purpose in PURPOSES}
    for purpose in PURPOSES:
        prefix = f"OLLOMI_{purpose.upper()}"
        indexes = sorted(
            {
                int(key[len(prefix) :].split("_", 1)[0])
                for key in os.environ
                if key.startswith(prefix)
                and key[len(prefix) :].split("_", 1)[0].isdigit()
                and "_" in key[len(prefix) :]
            }
        )
        for index in indexes:
            base = f"{prefix}{index}_"
            provider = os.getenv(base + "PROVIDER", "custom").strip().lower()
            if provider not in PROVIDER_DEFAULTS:
                raise ValueError(f"Unsupported provider in {base}PROVIDER")
            default_url, default_external = PROVIDER_DEFAULTS[provider]
            if provider == "ollama":
                default_url = settings().ollama_url
            elif provider == "whisper":
                default_url = settings().stt_url
            model = os.getenv(base + "MODEL", "").strip()
            url = os.getenv(base + "URL", default_url or "").strip()
            if not model or not url:
                raise ValueError(f"{base}MODEL and {base}URL/provider are required")
            options_text = os.getenv(base + "OPTIONS", "{}").strip() or "{}"
            try:
                options = json.loads(options_text)
            except json.JSONDecodeError as error:
                raise ValueError(f"{base}OPTIONS must be a JSON object") from error
            if not isinstance(options, dict):
                raise ValueError(f"{base}OPTIONS must be a JSON object")
            external = _env_bool(os.getenv(base + "EXTERNAL"), default_external)
            dimensions_text = os.getenv(base + "DIMENSIONS", "").strip()
            dimensions = int(dimensions_text) if dimensions_text else None
            if dimensions is not None and dimensions < 1:
                raise ValueError(f"{base}DIMENSIONS must be positive")
            configured[purpose].append(
                {
                    "id": str(uuid5(NAMESPACE_URL, f"ollomi:env:{purpose}:{index}")),
                    "name": os.getenv(base + "NAME", f"{provider} · {model}"),
                    "purpose": purpose,
                    "provider": provider.replace("_", "-"),
                    "priority": index,
                    "base_url": validate_url(url, external, allow_unresolved=True),
                    "model": model,
                    "api_key": os.getenv(base + "API_KEY", ""),
                    "external": external,
                    "options": options,
                    "dimensions": dimensions,
                }
            )
    embedding_dimensions = {profile["dimensions"] for profile in configured["embedding"]}
    if len(configured["embedding"]) > 1 and (None in embedding_dimensions or len(embedding_dimensions) != 1):
        raise ValueError("Embedding fallbacks require the same explicit *_DIMENSIONS value")
    return configured


def sync_env_profiles(db):
    configured = env_profiles()
    configured_ids = set()
    for purpose, profiles in configured.items():
        for item in profiles:
            configured_ids.add(item["id"])
            row = db.get(AIProfile, item["id"])
            is_new = row is None
            row = row or AIProfile(id=item["id"])
            previous = row.capabilities or {}
            old_key = unseal(row.encrypted_key) if row.encrypted_key else ""
            changed = not is_new and (
                row.name != item["name"]
                or row.base_url != item["base_url"]
                or row.model != item["model"]
                or row.external != item["external"]
                or old_key != item["api_key"]
                or previous.get("provider") != item["provider"]
                or previous.get("priority") != item["priority"]
                or previous.get("options") != item["options"]
                or previous.get("dimensions") != item["dimensions"]
            )
            row.name = item["name"]
            row.purpose = purpose
            row.base_url = item["base_url"]
            row.model = item["model"]
            if not row.encrypted_key or old_key != item["api_key"]:
                row.encrypted_key = seal(item["api_key"])
            row.enabled = True
            row.external = item["external"]
            row.capabilities = {
                **previous,
                "managed_by": "env",
                "provider": item["provider"],
                "priority": item["priority"],
                "options": item["options"],
                "dimensions": item["dimensions"],
            }
            if is_new or row.revision is None:
                row.revision = 1
            elif changed:
                row.revision += 1
            db.add(row)
    for row in db.scalars(select(AIProfile)):
        if (row.capabilities or {}).get("managed_by") == "env" and row.id not in configured_ids:
            row.enabled = False
    return configured


def env_managed(db, purpose):
    return bool(_ordered_env_rows(db, purpose))


def _ordered_env_rows(db, purpose):
    rows = list(
        db.scalars(
            select(AIProfile).where(
                AIProfile.purpose == purpose,
                AIProfile.enabled.is_(True),
            )
        )
    )
    rows = [row for row in rows if (row.capabilities or {}).get("managed_by") == "env"]
    return sorted(rows, key=lambda row: (row.capabilities or {}).get("priority", 999999))


def selected_profile(db, user_id, purpose):
    env_rows = _ordered_env_rows(db, purpose)
    if env_rows:
        profiles = [snapshot(row) for row in env_rows]
        return {**profiles[0], "fallbacks": profiles[1:]}
    user = db.get(User, user_id)
    profile_id = (user.preferences or {}).get("ai_profiles", {}).get(purpose)
    row = (
        db.get(AIProfile, profile_id)
        if profile_id
        else db.scalar(
            select(AIProfile).where(AIProfile.purpose == purpose, AIProfile.enabled.is_(True)).order_by(AIProfile.id)
        )
    )
    if row is None or not row.enabled or row.purpose != purpose:
        raise HTTPException(503, f"No enabled {purpose} profile")
    if row.external and settings().local_only:
        raise HTTPException(503, "External AI is disabled")
    return snapshot(row)


def profile_chain(profile):
    primary = {key: value for key, value in profile.items() if key != "fallbacks"}
    return [primary, *profile.get("fallbacks", [])]


def _failure_reason(error):
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status in {401, 403}:
            return "auth"
        if status == 429:
            return "quota"
        if status >= 500:
            return "provider_5xx"
    return "other"


def mark_profile_health(profile, healthy, reason=None):
    profile_id = profile.get("id")
    if not profile_id:
        return
    timestamp = datetime.now(timezone.utc).isoformat()
    with transaction() as db:
        row = db.get(AIProfile, profile_id)
        if row is None:
            return
        capabilities = dict(row.capabilities or {})
        runtime = dict(capabilities.get("runtime", {}))
        runtime.update(status="healthy" if healthy else "unhealthy", last_checked_at=timestamp)
        if healthy:
            runtime["last_success_at"] = timestamp
            runtime.pop("failure_reason", None)
        else:
            runtime["last_failure_at"] = timestamp
            runtime["failure_reason"] = reason or "other"
        row.capabilities = {**capabilities, "runtime": runtime}


def call_with_fallback(profile, operation):
    candidates = profile_chain(profile)
    transitions = []
    last_error = None
    for index, candidate in enumerate(candidates):
        try:
            result = operation(candidate)
            mark_profile_health(candidate, True)
            for previous, current, reason in transitions:
                record_fallback(
                    purpose=profile["purpose"],
                    from_profile=previous.get("id"),
                    to_profile=current.get("id"),
                    reason=reason,
                    outcome="recovered",
                )
            return result
        except Exception as error:
            last_error = error
            reason = _failure_reason(error)
            mark_profile_health(candidate, False, reason)
            if index + 1 < len(candidates):
                transitions.append((candidate, candidates[index + 1], reason))
                continue
            record_fallback(
                purpose=profile["purpose"],
                from_profile=candidate.get("id"),
                to_profile=None,
                reason=reason,
                outcome="exhausted",
            )
    raise last_error


def provider_client(profile, timeout=300):
    if profile.get("id"):
        with transaction() as db:
            current = db.get(AIProfile, profile["id"])
            if current is None or not current.enabled:
                raise HTTPException(503, "Inference profile is disabled")
    validate_url(profile["base_url"], profile.get("external", False))
    key = unseal(profile.get("encrypted_key", ""))
    return httpx.Client(
        base_url=profile["base_url"].rstrip("/") + "/",
        headers={"Authorization": f"Bearer {key}"} if key else {},
        timeout=httpx.Timeout(timeout, connect=10),
        follow_redirects=False,
        trust_env=False,
    )


def chat_request(profile, messages, stream=False):
    options = dict(profile.get("capabilities", {}).get("options", {}))
    suffix = options.pop("prompt_suffix", "")
    if suffix:
        messages = [dict(message) for message in messages]
        messages[-1]["content"] += "\n" + suffix
    return {
        "model": profile["model"],
        "messages": messages,
        "stream": stream,
        "max_tokens": 2048,
        **options,
    }


def completion(profile, messages, *, json_output=False, tools=None, fallback=True):
    def request(candidate):
        body = chat_request(candidate, messages)
        if json_output:
            body["response_format"] = {"type": "json_object"}
        if tools:
            body["tools"] = tools
        with provider_client(candidate) as client:
            response = client.post("chat/completions", json=body)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]

    if fallback:
        return call_with_fallback(profile, request)
    return request(profile)


def embed(profile, texts, *, fallback=True):
    if not texts:
        return []

    def request(candidate):
        dimensions = (candidate.get("capabilities") or {}).get("dimensions")
        body = {"model": candidate["model"], "input": texts}
        if dimensions:
            body["dimensions"] = dimensions
        with provider_client(candidate) as client:
            response = client.post("embeddings", json=body)
            response.raise_for_status()
            rows = sorted(response.json()["data"], key=lambda item: item["index"])
            vectors = [row["embedding"] for row in rows]
        if (
            len(vectors) != len(texts)
            or not vectors
            or not vectors[0]
            or any(len(v) != len(vectors[0]) for v in vectors)
        ):
            raise ValueError("Invalid embedding response")
        return vectors

    if fallback:
        return call_with_fallback(profile, request)
    return request(profile)


def seed_profiles(db):
    configured = sync_env_profiles(db)
    defaults = [("stt", "small", settings().stt_url, "Whisper local")]
    if settings().seed_local_ollama:
        defaults.extend(
            [
                ("chat", "qwen3:4b", settings().ollama_url, "Ollama local"),
                (
                    "embedding",
                    "embeddinggemma",
                    settings().ollama_url,
                    "Embeddings locales",
                ),
            ]
        )
    for purpose, model, base_url, name in defaults:
        if configured[purpose] or db.scalar(select(AIProfile.id).where(AIProfile.purpose == purpose).limit(1)):
            continue
        db.add(
            AIProfile(
                name=name,
                purpose=purpose,
                model=model,
                base_url=base_url,
                encrypted_key=seal(""),
            )
        )
