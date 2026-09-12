"""Omi Android compatibility routes. Values describe this local installation."""

import json
from datetime import timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from selfhost.db import Record, User, now, owned, transaction, wire
from selfhost.records import delete_record, update_conversation
from selfhost.security import current_user

router = APIRouter()


@router.get("/privacy", response_class=HTMLResponse)
def privacy():
    return '<!doctype html><html lang="es"><meta charset="utf-8"><title>Ollomi</title><h1>Datos en Ollomi</h1><p>Esta instalación guarda cuentas, grabaciones, transcripciones, recuerdos y tareas en el servidor administrado por su propietario. No utiliza Firebase ni envía telemetría.</p><p>Los administradores eligen los servidores de inteligencia artificial. Si habilitan un proveedor externo, el contenido necesario para esa operación se envía al proveedor seleccionado. Las grabaciones se conservan hasta su eliminación o hasta la fecha de retención configurada.</p><p>La exportación y eliminación están disponibles en la aplicación. Las copias de seguridad las administra el propietario del servidor. Ollomi se distribuye con la licencia del repositorio, sin garantía.</p></html>'


@router.get("/v1/account/cutover/control")
def control(user=Depends(current_user)):
    # The fork uses one local data generation; no Omi cloud migration exists here.
    return {
        "state": "legacy",
        "account_generation": 0,
        "ui_generation": 0,
        "api_generation": 0,
        "client_action": "none",
        "offline_queue_instruction": "none",
        "stranded_new_data": False,
        "legacy_writes_allowed": True,
        "product_traffic_allowed": True,
        "auth_bootstrap_reachable": True,
    }


def usage_for(uid, since=None):
    with transaction() as db:
        query = select(Record).where(
            Record.user_id == uid, Record.kind.in_(["conversation", "memory"])
        )
        if since:
            query = query.where(Record.created_at >= since)
        rows = list(db.scalars(query))
    conversations = [r for r in rows if r.kind == "conversation"]
    seconds = sum(
        max(0, float(s.get("end", 0)) - float(s.get("start", 0)))
        for r in conversations
        for s in r.data.get("transcript_segments", [])
    )
    return {
        "speech_seconds": int(seconds),
        "transcription_seconds": int(seconds),
        "words_transcribed": sum(
            len(s.get("text", "").split())
            for r in conversations
            for s in r.data.get("transcript_segments", [])
        ),
        "insights_gained": sum(r.kind == "memory" for r in rows),
        "memories_created": len(conversations),
    }


@router.get("/v1/users/me/usage")
def usage(user=Depends(current_user)):
    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "today": usage_for(user.id, today),
        "monthly": usage_for(user.id, today.replace(day=1)),
        "yearly": usage_for(user.id, today.replace(month=1, day=1)),
        "all_time": usage_for(user.id),
        "history": [],
    }


@router.get("/v1/users/me/subscription")
def subscription(user=Depends(current_user)):
    used = usage_for(user.id)
    return {
        "subscription": {"plan": "basic", "status": "active", "limits": {}},
        "show_subscription_ui": False,
        "available_plans": [],
        "chat_quota_allowed": True,
        "transcription_allowance": {"mode": "managed", "reason": "self_hosted"},
        **{
            key + "_used": used[key]
            for key in ["transcription_seconds", "words_transcribed", "insights_gained"]
        },
        **{
            key + "_limit": 0
            for key in ["transcription_seconds", "words_transcribed", "insights_gained"]
        },
    }


@router.get("/v1/fair-use/status")
def fair_use(user=Depends(current_user)):
    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "case_ref": "",
        "message": "",
        "stage": "none",
        "speech_hours_today": usage_for(user.id, today)["speech_seconds"] / 3600,
        "speech_hours_3day": usage_for(user.id, today - timedelta(days=2))[
            "speech_seconds"
        ]
        / 3600,
        "speech_hours_weekly": usage_for(user.id, today - timedelta(days=6))[
            "speech_seconds"
        ]
        / 3600,
        "limits": {"daily_hours": 0, "three_day_hours": 0, "weekly_hours": 0},
        "usage_pct": {"daily": 0, "three_day": 0, "weekly": 0},
        "dg_budget": {
            "daily_limit_ms": 0,
            "used_ms": 0,
            "remaining_ms": 0,
            "exhausted": False,
            "resets_at": "",
        },
    }


@router.get("/v1/users/store-recording-permission")
def recording_permission(user=Depends(current_user)):
    return {
        "store_recording_permission": bool(
            user.preferences.get("store_recordings", True)
        )
    }


@router.post("/v1/users/store-recording-permission")
def save_recording_permission(value: bool, user=Depends(current_user)):
    with transaction() as db:
        row = db.get(User, user.id)
        row.preferences = {**row.preferences, "store_recordings": value}
    return {"status": "ok"}


@router.post("/v1/users/geolocation")
def location(body: dict, user=Depends(current_user)):
    with transaction() as db:
        row = db.get(User, user.id)
        row.preferences = {**row.preferences, "geolocation": body}
    return {"status": "ok"}


@router.get("/v1/conversations/search")
@router.post("/v1/conversations/search")
def search_conversations(
    query: str = "", body: dict = Body(default={}), user=Depends(current_user)
):
    from selfhost.search import semantic_search

    phrase = body.get("query", query)
    hits = semantic_search(user.id, phrase, 50) if phrase.strip() else []
    return {
        "conversations": [
            hit["record"] for hit in hits if hit["kind"] == "conversation"
        ]
    }


@router.patch("/v1/conversations/{record_id}/folder")
def move(record_id: str, body: dict, user=Depends(current_user)):
    return update_conversation(record_id, {"folder_id": body.get("folder_id")}, user)


@router.post("/v1/folders/{folder_id}/conversations/bulk-move")
def bulk_move(folder_id: str, body: dict, user=Depends(current_user)):
    with transaction() as db:
        owned(db, user.id, folder_id, "folder")
        rows = [
            owned(db, user.id, rid, "conversation")
            for rid in body.get("conversation_ids", [])
        ]
        for row in rows:
            row.data = {**row.data, "folder_id": folder_id}
    return {"status": "ok"}


@router.get("/v1/conversations/{record_id}/transcripts")
def transcripts(record_id: str, user=Depends(current_user)):
    with transaction() as db:
        row = owned(db, user.id, record_id, "conversation")
        return {"prerecorded": row.data.get("transcript_segments", [])}


@router.patch("/v3/memories/{record_id}/review")
def review(record_id: str, value: bool, user=Depends(current_user)):
    with transaction() as db:
        row = owned(db, user.id, record_id, "memory")
        row.data = {**row.data, "reviewed": value}
    return {"status": "ok"}


@router.delete("/v3/memories")
def clear_memories(user=Depends(current_user)):
    with transaction() as db:
        ids = list(
            db.scalars(
                select(Record.id).where(
                    Record.user_id == user.id, Record.kind == "memory"
                )
            )
        )
    for record_id in ids:
        delete_record(user.id, record_id, "memory")
    return {"status": "ok"}


@router.get("/v1/conversations/{record_id}/export")
def conversation_export(
    record_id: str,
    format: str = Query("json", pattern="^(json|txt|md)$"),
    user=Depends(current_user),
):
    from fastapi.responses import Response

    with transaction() as db:
        row = owned(db, user.id, record_id, "conversation")
        data = wire(row)
    if format == "json":
        text, mime = json.dumps(data, ensure_ascii=False), "application/json"
    else:
        text = (
            data["structured"]["title"]
            + "\n\n"
            + data["structured"]["overview"]
            + "\n\n"
        )
        text += "\n".join(
            f"[{s['start']:.1f}] {s.get('speaker') or '?'}: {s['text']}"
            for s in data["transcript_segments"]
        )
        mime = "text/plain; charset=utf-8"
    return Response(
        text,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="conversation.{format}"'
        },
    )


@router.delete("/v1/users/delete-account")
def delete_account(user=Depends(current_user)):
    if user.admin:
        raise HTTPException(
            409,
            "An administrator must transfer administration before deleting this account",
        )
    from selfhost.audio import storage_path

    with transaction() as db:
        files = list(
            db.scalars(
                select(Record.id).where(
                    Record.user_id == user.id, Record.kind == "file"
                )
            )
        )
        from selfhost.search import purge_owner_index
        import httpx

        db.delete(db.get(User, user.id))
        db.flush()  # Fence concurrent indexing before deleting its derived copy.
        try:
            purge_owner_index(user.id)
        except httpx.HTTPError:
            raise HTTPException(
                503, "Search cleanup unavailable; account retained, retry deletion"
            ) from None
        for file_id in files:
            storage_path(user.id, file_id).unlink(missing_ok=True)
    return {"status": "ok"}


@router.delete("/v1/users/store-recording-permission")
def delete_recordings(user=Depends(current_user)):
    from selfhost.db import Job

    with transaction() as db:
        row = db.get(User, user.id)
        row.preferences = {**row.preferences, "store_recordings": False}
        files = list(
            db.scalars(
                select(Record).where(Record.user_id == user.id, Record.kind == "file")
            )
        )
        for file in files:
            db.delete(file)
        for job in db.scalars(
            select(Job)
            .where(
                Job.user_id == user.id,
                Job.kind == "audio",
                Job.status.in_(["queued", "running", "failed"]),
            )
            .with_for_update()
        ):
            job.status, job.lease_token = "cancelled", None
        for conversation in db.scalars(
            select(Record).where(
                Record.user_id == user.id, Record.kind == "conversation"
            )
        ):
            conversation.data = {**conversation.data, "file_ids": [], "audio_files": []}
        db.add(
            Job(
                user_id=user.id,
                kind="purge_files",
                payload={"file_ids": [file.id for file in files]},
            )
        )
    return {"status": "ok"}


@router.get("/v1/users/profile")
def user_profile(user=Depends(current_user)):
    return {
        "uid": user.id,
        "email": user.email,
        "name": user.name,
        "data_protection_level": "standard",
        "time_zone": user.preferences.get("time_zone", "UTC"),
    }


@router.get("/v1/users/language")
def user_language(user=Depends(current_user)):
    return {"language": user.preferences.get("language")}


@router.get("/v1/users/available-languages")
def available_languages(user=Depends(current_user)):
    # Whisper language codes; region-specific dialects use their base language.
    languages = {
        "English": "en",
        "Español": "es",
        "Català": "ca",
        "Galego": "gl",
        "Euskara": "eu",
        "Français": "fr",
        "Deutsch": "de",
        "Italiano": "it",
        "Português": "pt",
        "Nederlands": "nl",
        "Polski": "pl",
        "Українська": "uk",
        "Русский": "ru",
        "العربية": "ar",
        "हिन्दी": "hi",
        "中文": "zh",
        "日本語": "ja",
        "한국어": "ko",
        "Türkçe": "tr",
        "Svenska": "sv",
    }
    return {
        "languages": [{"name": name, "code": code} for name, code in languages.items()]
    }


@router.patch("/v1/users/language")
def set_language(body: dict, user=Depends(current_user)):
    import re

    language = body.get("language")
    if not isinstance(language, str) or not re.fullmatch(
        r"[a-z]{2,3}(?:-[A-Za-z]{2,4})?", language
    ):
        raise HTTPException(422, "Invalid language code")
    with transaction() as db:
        row = db.get(User, user.id)
        row.preferences = {**row.preferences, "language": language.split("-")[0]}
        return {
            "status": "ok",
            "single_language_mode": row.preferences.get("single_language_mode", False),
        }


@router.get("/v1/users/onboarding")
def onboarding(user=Depends(current_user)):
    return {
        "completed": user.preferences.get("onboarding_completed", False),
        "device_onboarding_completed": user.preferences.get(
            "device_onboarding_completed", False
        ),
    }


@router.patch("/v1/users/onboarding")
def set_onboarding(body: dict, user=Depends(current_user)):
    allowed = {
        "completed": "onboarding_completed",
        "device_onboarding_completed": "device_onboarding_completed",
    }
    changes = {}
    for key, target in allowed.items():
        if key in body:
            if not isinstance(body[key], bool):
                raise HTTPException(422, "Expected a boolean")
            changes[target] = body[key]
    with transaction() as db:
        row = db.get(User, user.id)
        row.preferences = {**row.preferences, **changes}
    return {"status": "ok"}


@router.get("/v1/users/private-cloud-sync")
def private_cloud_sync(user=Depends(current_user)):
    return {"private_cloud_sync_enabled": False}


@router.get("/v1/users/training-data-opt-in")
def training_data(user=Depends(current_user)):
    return {"opted_in": False, "status": None}


@router.get("/v1/users/transcription-preferences")
def transcription_preferences(user=Depends(current_user)):
    return {"single_language_mode": False, "vocabulary": []}
