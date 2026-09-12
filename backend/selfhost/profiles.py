import ipaddress
import socket
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from selfhost.config import settings
from selfhost.db import AIProfile, User, transaction
from selfhost.security import seal, unseal


def validate_url(value: str, external: bool = False):
    url = urlsplit(value)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise HTTPException(
            422, "Use an HTTP(S) base URL without credentials, query or fragment"
        )
    if external and settings().local_only:
        raise HTTPException(422, "External providers require OLLOMI_LOCAL_ONLY=false")
    try:
        addresses = {
            ipaddress.ip_address(info[4][0])
            for info in socket.getaddrinfo(url.hostname, url.port or 443)
        }
    except socket.gaierror:
        raise HTTPException(422, "Server hostname cannot be resolved") from None
    for address in addresses:
        if address.is_link_local or address.is_multicast or address.is_unspecified:
            raise HTTPException(422, "This network address is not allowed")
        if not external and not (address.is_private or address.is_loopback):
            raise HTTPException(
                422, "Public servers must be explicitly marked external"
            )
    if external and url.scheme != "https":
        raise HTTPException(422, "External providers require HTTPS")
    return value.rstrip("/")


def public_profile(row, admin=False):
    result = {
        "id": row.id,
        "name": row.name,
        "purpose": row.purpose,
        "model": row.model,
        "enabled": row.enabled,
        "external": row.external,
        "capabilities": row.capabilities,
        "revision": row.revision,
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
    }


def selected_profile(db, user_id, purpose):
    user = db.get(User, user_id)
    profile_id = (user.preferences or {}).get("ai_profiles", {}).get(purpose)
    row = (
        db.get(AIProfile, profile_id)
        if profile_id
        else db.scalar(
            select(AIProfile)
            .where(AIProfile.purpose == purpose, AIProfile.enabled.is_(True))
            .order_by(AIProfile.id)
        )
    )
    if row is None or not row.enabled or row.purpose != purpose:
        raise HTTPException(503, f"No enabled {purpose} profile")
    if row.external and settings().local_only:
        raise HTTPException(503, "External AI is disabled")
    return snapshot(row)


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


def completion(profile, messages, *, json_output=False, tools=None):
    body = chat_request(profile, messages)
    if json_output:
        body["response_format"] = {"type": "json_object"}
    if tools:
        body["tools"] = tools
    with provider_client(profile) as client:
        response = client.post("chat/completions", json=body)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]


def embed(profile, texts):
    if not texts:
        return []
    with provider_client(profile) as client:
        response = client.post(
            "embeddings", json={"model": profile["model"], "input": texts}
        )
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


def seed_profiles(db):
    if db.scalar(select(AIProfile.id).limit(1)):
        return
    for purpose, model, base_url, name in [
        ("stt", "small", settings().stt_url, "Whisper local"),
        ("chat", "qwen3:4b", settings().ollama_url, "Ollama local"),
        ("embedding", "embeddinggemma", settings().ollama_url, "Embeddings locales"),
    ]:
        db.add(
            AIProfile(
                name=name,
                purpose=purpose,
                model=model,
                base_url=base_url,
                encrypted_key=seal(""),
            )
        )
