from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from selfhost import (
    admin,
    audio,
    chat,
    records,
    search,
    mobile,
    voiceprint,
    sync,
    playback,
    tts,
    integrations,
    firmware,
    mcp_server,
    rate_limit,
    knowledge_graph,
    static_map,
)
from selfhost.config import settings
from selfhost.db import Instance, ident, transaction
from selfhost.accounts import seed_admin_from_env
from selfhost.profiles import seed_profiles


def initialize():
    settings().validate_runtime()
    with transaction() as db:
        if db.get(Instance, "id") is None:
            db.add(Instance(key="id", value=ident()))
        seed_admin_from_env(db)
        seed_profiles(db)


@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(initialize)
    yield


app = FastAPI(title="Ollomi", version="0.1.0", lifespan=lifespan)
for router in (
    firmware.router,
    mcp_server.router,
    integrations.router,
    tts.router,
    playback.router,
    sync.router,
    mobile.router,
    voiceprint.router,
    admin.router,
    audio.router,
    chat.router,
    search.router,
    records.router,
    knowledge_graph.router,
    static_map.router,
):
    app.include_router(router)


@app.get("/health")
def health():
    """Liveness probe: the process can answer requests."""
    return {"status": "ok"}


@app.get("/health/ready")
def readiness():
    """Readiness probe: every durable dependency used by the API is reachable."""
    with transaction() as db:
        db.execute(text("SELECT 1"))
    try:
        rate_limit.redis().ping()
        with search.typesense() as client:
            response = client.get("health")
            response.raise_for_status()
            state = response.json()
            if state.get("ok") is not True or state.get("resource_error"):
                raise RuntimeError("Typesense is not ready")
    except Exception:
        # Dependency details belong in server logs, never in a public health response.
        raise HTTPException(status_code=503, detail="Ollomi dependencies unavailable") from None
    return {"status": "ok"}


@app.get("/v1/server-info")
def server_info():
    with transaction() as db:
        instance = db.get(Instance, "id")
        capabilities = [
            "audio_import",
            "live_transcription",
            "conversations",
            "memories",
            "tasks",
            "structured_extraction",
            "goals",
            "calendar_events",
            "decisions",
            "chat",
            "search",
            "ai_profiles",
            "env_ai_fallbacks",
            "ai_provider_status",
            "events",
            "knowledge_graph",
            "static_maps",
        ]
        response = {
            "name": "Ollomi",
            "instance_id": instance.value,
            "version": "0.1.0",
            "protocol_version": 1,
            "authentication": "local",
            "local_only": settings().local_only,
            "model_selection_allowed": settings().allow_user_model_selection,
            "capabilities": capabilities,
        }
        if settings().allow_user_model_selection:
            capabilities.append("ai_model_selection")
        if settings().mcp_enabled:
            capabilities.append("mcp")
            response["mcp_url"] = settings().mcp_public_url.rstrip("/") + "/mcp"
        if settings().voiceprint_url:
            capabilities.append("voiceprint")
            capabilities.append("speaker_diarization")
        return response
