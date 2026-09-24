"""Durable import of Omi's length-prefixed device/phone WAL files."""

import hashlib
import os
import re
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import jwt
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from selfhost.audio import enqueue_audio, job_wire, storage_path
from selfhost.config import settings
from selfhost.db import Job, Record, ident, owned, transaction
from selfhost.security import current_user

router = APIRouter()


def decode_bin(source, destination, filename):
    match = re.search(r"_(lc3_fs1030|pcm16|pcm8|opus_fs320|opus)_(\d+)_(\d+)_fs(\d+)_", filename)
    if not match:
        raise HTTPException(422, "Unsupported WAL codec or filename")
    codec, rate, channels, frame_size = match.groups()
    rate, channels, frame_size = int(rate), int(channels), int(frame_size)
    if rate not in {8000, 16000, 24000, 48000} or channels not in {1, 2} or frame_size > rate * 120 // 1000:
        raise HTTPException(422, "Invalid WAL audio parameters")
    if codec == "lc3_fs1030" and (rate, channels, frame_size) != (16000, 1, 160):
        raise HTTPException(422, "Invalid Friend Pendant WAL audio parameters")
    width = 1 if codec == "pcm8" else 2
    decoder = None
    if codec in {"opus", "opus_fs320"}:
        import opuslib

        decoder = opuslib.Decoder(rate, channels)
    elif codec == "lc3_fs1030":
        from selfhost.lc3_audio import Lc3Decoder

        decoder = Lc3Decoder()
    samples = 0
    with source.open("rb") as input_file, wave.open(str(destination), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        while prefix := input_file.read(4):
            if len(prefix) != 4:
                raise HTTPException(422, "Truncated WAL length prefix; original must be kept")
            length = struct.unpack("<I", prefix)[0]
            if not 0 < length <= 65536:
                raise HTTPException(422, "Invalid WAL frame length")
            frame = input_file.read(length)
            if len(frame) != length:
                raise HTTPException(422, "Truncated WAL frame; original must be kept")
            if decoder:
                try:
                    frame = decoder.decode(frame) if codec == "lc3_fs1030" else decoder.decode(frame, frame_size)
                except ValueError as error:
                    raise HTTPException(422, str(error)) from error
            if len(frame) % (width * channels):
                raise HTTPException(422, "Misaligned PCM frame")
            samples += len(frame) // (width * channels)
            if samples > rate * settings().max_audio_seconds:
                raise HTTPException(413, "Recording exceeds maximum duration")
            output.writeframes(frame)
    if not samples:
        raise HTTPException(422, "Empty WAL")


@router.post("/v2/sync-capture-manifest")
def manifest(body: dict, user=Depends(current_user)):
    from datetime import timedelta
    from selfhost.db import now

    with transaction() as db:
        owned(db, user.id, body.get("conversation_id"), "conversation")
    claims = {
        "sub": user.id,
        "conversation_id": body["conversation_id"],
        "files": body.get("files", []),
        "aud": "ollomi-sync",
        "exp": now() + timedelta(hours=1),
    }
    return {"manifest": jwt.encode(claims, settings().secret_key.get_secret_value(), algorithm="HS256")}


def accept_files(uid, paths, names, receipt, conversation_id, language="auto"):
    receipt_id = str(uuid5(NAMESPACE_URL, f"ollomi:sync:{uid}:{receipt}"))
    with transaction() as db:
        previous = db.get(Record, receipt_id)
        if previous:
            return db.get(Job, previous.data["job_id"]).id
        if conversation_id:
            existing = owned(db, uid, conversation_id, "conversation")
            # A stamped conversation already carries the language its live
            # segment was captured with; keep every part on the same language.
            language = (existing.data or {}).get("language") or language
    file_id = ident()
    destination = storage_path(uid, file_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            tempfile.TemporaryDirectory(dir=settings().data_dir) as temporary,
            wave.open(str(destination), "wb") as combined,
        ):
            combined.setnchannels(1)
            combined.setsampwidth(2)
            combined.setframerate(16000)
            samples = 0
            for index, (path, name) in enumerate(zip(paths, names)):
                decoded = Path(temporary) / f"{index}.wav"
                normalized = Path(temporary) / f"{index}-16k.wav"
                decode_bin(path, decoded, name)
                subprocess.run(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-v",
                        "error",
                        "-i",
                        str(decoded),
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        "-c:a",
                        "pcm_s16le",
                        str(normalized),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=600,
                )
                with wave.open(str(normalized), "rb") as source:
                    while chunk := source.readframes(16000 * 30):
                        samples += len(chunk) // 2
                        if samples > 16000 * settings().max_audio_seconds:
                            raise HTTPException(413, "Batch exceeds maximum duration")
                        combined.writeframes(chunk)
        with destination.open("rb") as durable:
            os.fsync(durable.fileno())
        return enqueue_audio(
            uid,
            file_id,
            "omi-recording.wav",
            language,
            conversation_id=conversation_id,
            receipt_id=receipt_id,
            file_count=len(paths),
        )["job_id"]
    except IntegrityError:
        destination.unlink(missing_ok=True)
        with transaction() as db:
            previous = owned(db, uid, receipt_id, "sync_receipt")
            return previous.data["job_id"]
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


@router.post("/v2/sync-local-files", status_code=202)
async def sync_files(
    files: list[UploadFile] = File(...),
    conversation_id: str | None = None,
    user=Depends(current_user),
):
    if not 1 <= len(files) <= 100:
        raise HTTPException(422, "Upload 1–100 WAL files")
    digest = hashlib.sha256()
    total = 0
    try:
        with tempfile.TemporaryDirectory(dir=settings().data_dir) as temporary:
            paths, names = [], []
            for index, file in enumerate(files):
                name = file.filename or ""
                if Path(name).name != name or "\\" in name or not name.endswith(".bin"):
                    raise HTTPException(422, "Invalid WAL filename")
                path = Path(temporary) / f"{index}.bin"
                digest.update(name.encode() + b"\x00")
                with path.open("wb") as output:
                    while chunk := await file.read(1024 * 1024):
                        total += len(chunk)
                        if total > settings().max_upload_mb * 1024 * 1024:
                            raise HTTPException(413, "Batch exceeds upload limit")
                        digest.update(chunk)
                        await run_in_threadpool(output.write, chunk)
                paths.append(path)
                names.append(name)
            job_id = await run_in_threadpool(
                accept_files,
                user.id,
                paths,
                names,
                digest.hexdigest(),
                conversation_id,
                (user.preferences or {}).get("language") or "auto",
            )
            return {
                "job_id": job_id,
                "status": "queued",
                "total_files": len(files),
                "total_segments": len(files),
                "poll_after_ms": 3000,
            }
    finally:
        for file in files:
            await file.close()


@router.get("/v2/sync-local-files/{job_id}")
def sync_status(job_id: str, user=Depends(current_user)):
    with transaction() as db:
        job = db.get(Job, job_id)
        if not job or job.user_id != user.id:
            raise HTTPException(404, "Job not found")
        count = job.payload.get("file_count", 1)
        success = job.status == "completed"
        return {
            **job_wire(job),
            "status": "failed" if job.status == "cancelled" else job.status,
            "total_segments": count,
            "processed_segments": count if success else 0,
            "successful_segments": count if success else 0,
            "failed_segments": count if job.status == "failed" else 0,
            "result": (
                {
                    "new_memories": [job.payload["conversation_id"]],
                    "updated_memories": [],
                    "total_segments": count,
                    "failed_segments": 0,
                }
                if success
                else None
            ),
        }
