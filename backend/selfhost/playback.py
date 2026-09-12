from datetime import timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from selfhost.audio import storage_path
from selfhost.config import settings
from selfhost.db import Session, User, now, owned, transaction
from selfhost.security import aware, bearer, current_user

router = APIRouter()


@router.post("/v1/sync/audio/{conversation_id}/precache")
def precache(conversation_id: str, user=Depends(current_user)):
    with transaction() as db:
        owned(db, user.id, conversation_id, "conversation")
    return {"status": "ready"}


@router.get("/v1/sync/audio/{conversation_id}/urls")
def urls(
    conversation_id: str,
    request: Request,
    user=Depends(current_user),
    credentials=Depends(bearer),
):
    claims = jwt.decode(
        credentials.credentials,
        settings().secret_key.get_secret_value(),
        algorithms=["HS256"],
        audience="ollomi-app",
        issuer="ollomi",
    )
    base = str(request.base_url).rstrip("/")
    if request.headers.get("x-forwarded-proto") == "https":
        base = base.replace("http://", "https://", 1)
    with transaction() as db:
        row = owned(db, user.id, conversation_id, "conversation")
        files = []
        for audio in row.data.get("audio_files", []):
            file_id = audio["id"]
            file = owned(db, user.id, file_id, "file")
            exists = storage_path(user.id, file_id).is_file()
            ticket = jwt.encode(
                {
                    "sub": user.id,
                    "sid": claims["sid"],
                    "file": file_id,
                    "aud": "ollomi-audio",
                    "exp": now() + timedelta(minutes=30),
                },
                settings().secret_key.get_secret_value(),
                algorithm="HS256",
            )
            files.append(
                {
                    "id": file_id,
                    "duration": audio["duration"],
                    "status": "cached" if exists else "unavailable",
                    "content_type": file.data["content_type"],
                    "signed_url": f"{base}/v1/audio/{file_id}?ticket={ticket}"
                    if exists
                    else None,
                }
            )
        return {"audio_files": files, "conversation_audio": None}


@router.get("/v1/audio/{file_id}")
def download(file_id: str, ticket: str):
    try:
        claims = jwt.decode(
            ticket,
            settings().secret_key.get_secret_value(),
            algorithms=["HS256"],
            audience="ollomi-audio",
        )
        if claims["file"] != file_id:
            raise ValueError("Different file")
        with transaction() as db:
            session = db.get(Session, claims["sid"])
            user = db.get(User, claims["sub"])
            if (
                not session
                or session.revoked
                or session.user_id != claims["sub"]
                or aware(session.expires_at) <= now()
                or not user
                or not user.enabled
            ):
                raise ValueError("Session expired")
            row = owned(db, user.id, file_id, "file")
            path = storage_path(user.id, file_id)
            if not path.is_file():
                raise HTTPException(404, "Audio no longer available")
            return FileResponse(
                path,
                media_type=row.data["content_type"],
                headers={
                    "Cache-Control": "private, no-store",
                    "Referrer-Policy": "no-referrer",
                },
            )
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Audio ticket expired") from None


@router.get("/v1/sync/audio/{conversation_id}/{file_id}")
def authenticated_download(
    conversation_id: str, file_id: str, user=Depends(current_user)
):
    with transaction() as db:
        conversation = owned(db, user.id, conversation_id, "conversation")
        if file_id not in conversation.data.get("file_ids", []):
            raise HTTPException(404, "Audio not in this conversation")
        file = owned(db, user.id, file_id, "file")
        path = storage_path(user.id, file_id)
        if not path.is_file():
            raise HTTPException(404, "Audio no longer available")
        return FileResponse(path, media_type=file.data["content_type"])
