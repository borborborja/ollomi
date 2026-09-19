from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from selfhost import (
    admin,
    audio,
    chat,
    records,
    search,
    mobile,
    sync,
    playback,
    tts,
    integrations,
    firmware,
)
from selfhost.config import settings
from selfhost.db import Instance, ident, transaction
from selfhost.profiles import seed_profiles


def initialize():
    settings().validate_runtime()
    with transaction() as db:
        if db.get(Instance, "id") is None:
            db.add(Instance(key="id", value=ident()))
        seed_profiles(db)


@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(initialize)
    yield


app = FastAPI(title="Ollomi", version="0.1.0", lifespan=lifespan)
for router in (
    firmware.router,
    integrations.router,
    tts.router,
    playback.router,
    sync.router,
    mobile.router,
    admin.router,
    audio.router,
    chat.router,
    search.router,
    records.router,
):
    app.include_router(router)


@app.get("/health")
def health():
    with transaction() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/v1/server-info")
def server_info():
    with transaction() as db:
        instance = db.get(Instance, "id")
        return {
            "name": "Ollomi",
            "instance_id": instance.value,
            "version": "0.1.0",
            "protocol_version": 1,
            "authentication": "local",
            "local_only": settings().local_only,
            "capabilities": [
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
            ],
        }
