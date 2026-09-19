import asyncio
import json
import mimetypes
import shutil
import os
import subprocess
import wave
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from selfhost.config import settings
from selfhost.db import Job, Record, emit, ident, owned, transaction
from selfhost.profiles import call_with_fallback, provider_client, selected_profile
from selfhost.records import conversation_data
from selfhost.security import authenticate, current_user

router = APIRouter()


def storage_path(uid, file_id):
    from uuid import UUID

    UUID(uid)
    UUID(file_id)
    return settings().data_dir / "files" / uid / file_id


def job_wire(job):
    return {
        "id": job.id,
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "result": job.result,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def enqueue_audio(
    uid,
    file_id,
    filename,
    language="auto",
    conversation_id=None,
    receipt_id=None,
    file_count=1,
):
    with transaction() as db:
        file_row = Record(
            id=file_id,
            user_id=uid,
            kind="file",
            data={
                "name": Path(filename).name,
                "content_type": mimetypes.guess_type(filename)[0]
                or "application/octet-stream",
            },
        )
        db.add(file_row)
        row = Record(
            id=conversation_id or ident(),
            user_id=uid,
            kind="conversation",
            data=conversation_data(
                {
                    "imported": conversation_id is None,
                    "file_ids": [file_id],
                    "language": language,
                }
            ),
        )
        if conversation_id:
            row = owned(db, uid, conversation_id, "conversation")
            row.data = {
                **row.data,
                "file_ids": [*row.data.get("file_ids", []), file_id],
                "status": "processing",
            }
        else:
            db.add(row)
        file_row.data = {**file_row.data, "conversation_id": row.id}
        job = Job(
            user_id=uid,
            payload={
                "file_id": file_id,
                "conversation_id": row.id,
                "language": language,
                "file_count": file_count,
                **{
                    p: selected_profile(db, uid, p)
                    for p in ("stt", "chat", "embedding")
                },
            },
        )
        db.add(job)
        db.flush()
        if receipt_id:
            db.add(
                Record(
                    id=receipt_id,
                    user_id=uid,
                    kind="sync_receipt",
                    data={"job_id": job.id},
                )
            )
        emit(db, uid, "audio_accepted", {"job_id": job.id, "conversation_id": row.id})
        return job_wire(job)


@router.post("/v1/import/audio", status_code=202)
async def import_audio(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    user=Depends(current_user),
):
    file_id = ident()
    destination = storage_path(user.id, file_id)
    await run_in_threadpool(destination.parent.mkdir, parents=True, exist_ok=True)
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if shutil.disk_usage(destination.parent).free < 256 * 1024 * 1024 + len(
                    chunk
                ):
                    raise HTTPException(
                        507, "Insufficient server storage; retry after freeing space"
                    )
                if size > settings().max_upload_mb * 1024 * 1024:
                    raise HTTPException(
                        413, "Audio exceeds the configured upload limit"
                    )
                await run_in_threadpool(output.write, chunk)
            await run_in_threadpool(output.flush)
            await run_in_threadpool(os.fsync, output.fileno())
        if not size:
            raise HTTPException(422, "Audio is empty")
        return await run_in_threadpool(
            enqueue_audio, user.id, file_id, file.filename or "audio.mp3", language
        )
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.get("/v1/import/jobs")
def jobs(user=Depends(current_user)):
    from sqlalchemy import select

    with transaction() as db:
        return {
            "jobs": [
                job_wire(j)
                for j in db.scalars(
                    select(Job)
                    .where(Job.user_id == user.id, Job.kind.in_(["audio", "enrich"]))
                    .order_by(Job.created_at.desc())
                    .limit(100)
                )
            ]
        }


@router.get("/v1/import/jobs/{job_id}")
def job_status(job_id: str, user=Depends(current_user)):
    with transaction() as db:
        job = db.get(Job, job_id)
        if not job or job.user_id != user.id:
            raise HTTPException(404, "Job not found")
        return job_wire(job)


@router.post("/v1/import/jobs/{job_id}/{operation}")
def job_action(job_id: str, operation: str, user=Depends(current_user)):
    from sqlalchemy import select

    with transaction() as db:
        job = db.scalar(
            select(Job)
            .where(Job.id == job_id, Job.user_id == user.id)
            .with_for_update()
        )
        if not job:
            raise HTTPException(404, "Job not found")
        if operation == "cancel" and job.status in {"queued", "running", "failed"}:
            job.status = "cancelled"
            job.lease_token = None
        elif operation == "retry" and job.status in {"failed", "cancelled"}:
            # An explicit retry uses the user's corrected/current provider choices.
            job.payload = {
                **job.payload,
                **{
                    purpose: selected_profile(db, user.id, purpose)
                    for purpose in ("stt", "chat", "embedding")
                    if purpose in job.payload
                },
            }
            job.status, job.error, job.progress, job.attempts = "queued", None, 0, 0
        else:
            raise HTTPException(409, "Job cannot perform this operation")
        return job_wire(job)


@router.get("/v1/files/{file_id}")
def download_file(file_id: str, user=Depends(current_user)):
    with transaction() as db:
        row = owned(db, user.id, file_id, "file")
        path = storage_path(user.id, file_id)
        if not path.is_file():
            raise HTTPException(404, "File not found")
        return FileResponse(
            path,
            filename=row.data["name"],
            media_type=row.data.get("content_type", "application/octet-stream"),
        )


def probe_audio(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            "mp3,wav,flac,ogg,mov,aac,matroska,webm",
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        timeout=30,
        check=True,
    )
    info = json.loads(result.stdout)
    duration = float(info.get("format", {}).get("duration", 0))
    if (
        not any(s.get("codec_type") == "audio" for s in info.get("streams", []))
        or duration <= 0
    ):
        raise ValueError("Invalid audio file")
    if duration > settings().max_audio_seconds:
        raise ValueError("Audio exceeds configured duration limit")
    return duration


def transcribe_file(profile, path, language="auto", diarize=True):
    def request(candidate):
        options = dict((candidate.get("capabilities") or {}).get("options", {}))
        response_format = options.pop("response_format", "verbose_json")
        data = {
            "model": candidate["model"],
            "response_format": response_format,
            **options,
        }
        if language != "auto":
            data["language"] = language
        if not candidate.get("external"):
            data["diarize"] = str(diarize).lower()
        with (
            provider_client(candidate, timeout=600) as client,
            Path(path).open("rb") as file,
        ):
            response = client.post(
                "audio/transcriptions",
                data=data,
                files={"file": ("audio.wav", file, "audio/wav")},
            )
            response.raise_for_status()
            result = response.json()
        if not isinstance(result.get("text"), str):
            raise ValueError("STT response has no text")
        return result

    result = call_with_fallback(profile, request)
    segments = result.get("segments")
    if segments is None:
        # A text-only provider cannot manufacture word/speaker timestamps.
        segments = [
            {
                "start": 0,
                "end": probe_audio(path),
                "text": result["text"],
                "speaker": None,
            }
        ]
    return [
        {
            "id": ident(),
            "start": float(s.get("start", 0)),
            "end": float(s.get("end", 0)),
            "text": s["text"],
            "speaker": s.get("speaker"),
            "is_user": False,
            "person_id": None,
            "translations": [],
        }
        for s in segments
        if s.get("text", "").strip()
    ]


@router.websocket("/v4/listen")
async def listen(socket: WebSocket):
    token = socket.headers.get("authorization", "").removeprefix("Bearer ")
    try:
        user = await run_in_threadpool(authenticate, token)
    except HTTPException:
        await socket.close(code=4401)
        return
    codec = socket.query_params.get("codec", "pcm16")
    if codec == "opus_fs320":
        codec = "opus"
    if codec not in {"pcm16", "pcm8", "opus"}:
        await socket.close(code=4400, reason="Supported codecs: pcm16, opus")
        return
    try:
        rate = int(socket.query_params.get("sample_rate", "16000"))
    except ValueError:
        await socket.close(code=4400, reason="Invalid sample rate")
        return
    if rate not in {8000, 16000, 24000, 48000}:
        await socket.close(code=4400, reason="Unsupported sample rate")
        return
    await socket.accept()
    file_id, conversation_id = (
        ident(),
        socket.query_params.get("conversation_id")
        or socket.query_params.get("client_conversation_id")
        or ident(),
    )

    def setup():
        with transaction() as db:
            row = db.get(Record, conversation_id)
            if row:
                owned(db, user.id, conversation_id, "conversation")
            else:
                db.add(
                    Record(
                        id=conversation_id,
                        user_id=user.id,
                        kind="conversation",
                        data=conversation_data({"status": "in_progress"}),
                    )
                )
            return selected_profile(db, user.id, "stt")

    try:
        profile = await run_in_threadpool(setup)
    except HTTPException:
        await socket.close(code=4404)
        return
    path = storage_path(user.id, file_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    decoder = None
    if codec == "opus":
        import opuslib

        decoder = opuslib.Decoder(rate, 1)
    await socket.send_json({"type": "last_memory", "memory_id": conversation_id})
    buffer = bytearray()
    total_samples = 0
    try:
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            while True:
                message = await asyncio.wait_for(socket.receive(), timeout=90)
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("text"):
                    if json.loads(message["text"]).get("type") in {"stop", "finish"}:
                        break
                    continue
                chunk = message.get("bytes", b"")
                if decoder:
                    chunk = decoder.decode(chunk, rate * 120 // 1000)
                if codec == "pcm8":
                    import audioop

                    chunk = audioop.lin2lin(audioop.bias(chunk, 1, -128), 1, 2)
                if len(chunk) % 2:
                    raise ValueError("Unaligned PCM16")
                total_samples += len(chunk) // 2
                if total_samples > rate * settings().max_audio_seconds:
                    break
                await run_in_threadpool(wav.writeframes, chunk)
                buffer.extend(chunk)
                if len(buffer) >= rate * 2 * 8:
                    preview = path.with_suffix(".preview.wav")
                    offset = (total_samples - len(buffer) // 2) / rate

                    def preview_transcript():
                        with wave.open(str(preview), "wb") as clip:
                            clip.setnchannels(1)
                            clip.setsampwidth(2)
                            clip.setframerate(rate)
                            clip.writeframes(bytes(buffer))
                        return transcribe_file(profile, preview, diarize=False)

                    segments = await run_in_threadpool(preview_transcript)
                    preview.unlink(missing_ok=True)
                    buffer.clear()
                    for s in segments:
                        s["start"] += offset
                        s["end"] += offset
                    if segments:
                        await socket.send_json(segments)
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception:
        try:
            await socket.send_json(
                {
                    "type": "error",
                    "message": "Live transcription interrupted; recorded audio will be processed",
                }
            )
        except Exception:
            pass
    finally:
        if total_samples:
            job = await run_in_threadpool(
                enqueue_audio,
                user.id,
                file_id,
                "recording.wav",
                "auto",
                conversation_id,
            )
            try:
                await socket.send_json({"type": "processing_started", **job})
            except Exception:
                pass
        else:
            path.unlink(missing_ok=True)
