import asyncio
import json
import mimetypes
import shutil
import os
import subprocess
import time
import wave
from pathlib import Path
from urllib.parse import urlsplit

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
from selfhost.db import Job, Record, User, emit, ident, owned, transaction
from selfhost.profiles import call_with_fallback, provider_client, selected_profile
from selfhost.records import conversation_data
from selfhost.security import authenticate, current_user
from selfhost.stt_filter import filter_silent_hallucinations

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
        user = db.get(User, uid)
        retain_audio = bool(user and user.preferences.get("private_cloud_sync_enabled", False))
        file_row = Record(
            id=file_id,
            user_id=uid,
            kind="file",
            data={
                "name": Path(filename).name,
                "content_type": mimetypes.guess_type(filename)[0] or "application/octet-stream",
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
                # Snapshot the user's choice when audio is admitted. A later
                # settings change must not rewrite the retention contract of a
                # queued or running recording.
                "retain_audio": retain_audio,
                "vocabulary": [
                    word
                    for word in ((user.preferences or {}).get("vocabulary") or [])
                    if isinstance(word, str) and word.strip()
                ]
                if user
                else [],
                **{p: selected_profile(db, uid, p) for p in ("stt", "chat", "embedding")},
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
                if shutil.disk_usage(destination.parent).free < 256 * 1024 * 1024 + len(chunk):
                    raise HTTPException(507, "Insufficient server storage; retry after freeing space")
                if size > settings().max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "Audio exceeds the configured upload limit")
                await run_in_threadpool(output.write, chunk)
            await run_in_threadpool(output.flush)
            await run_in_threadpool(os.fsync, output.fileno())
        if not size:
            raise HTTPException(422, "Audio is empty")
        return await run_in_threadpool(enqueue_audio, user.id, file_id, file.filename or "audio.mp3", language)
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
        job = db.scalar(select(Job).where(Job.id == job_id, Job.user_id == user.id).with_for_update())
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
    if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])) or duration <= 0:
        raise ValueError("Invalid audio file")
    if duration > settings().max_audio_seconds:
        raise ValueError("Audio exceeds configured duration limit")
    return duration


def transcribe_file(profile, path, language="auto", diarize=True, vocabulary=None):
    # The user's custom vocabulary biases recognition of names and jargon. Each
    # provider exposes it differently, so it is passed to the adapters instead
    # of being written into provider options.
    vocabulary = [word for word in (vocabulary or []) if isinstance(word, str) and word.strip()]

    def openai_compatible(candidate):
        options = dict((candidate.get("capabilities") or {}).get("options", {}))
        response_format = options.pop("response_format", "verbose_json")
        data = {
            "model": candidate["model"],
            "response_format": response_format,
            **options,
        }
        # Whisper-family endpoints treat `prompt` as recognition context, but a
        # model that hears noise/music emits the prompt verbatim (the
        # "Elegiroscopi.com" / "EGIRGORSOPI" class of artefacts). The user's
        # vocabulary is therefore never injected here: it reaches providers only
        # through their native biasing APIs (Deepgram keywords, AssemblyAI
        # word_boost, Gemini custom_vocabulary) or an explicit admin-configured
        # prompt/hotwords in provider OPTIONS.
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
            return response.json()

    def deepgram(candidate):
        options = dict((candidate.get("capabilities") or {}).get("options", {}))
        params = {
            "model": candidate["model"],
            "smart_format": "true",
            "diarize": str(diarize).lower(),
            "utterances": "true",
            **options,
        }
        if language != "auto":
            params["language"] = language
        if vocabulary:
            # Deepgram repeats the keyword query parameter for each term.
            params["keywords"] = vocabulary
        with provider_client(candidate, timeout=600) as client, Path(path).open("rb") as file:
            response = client.post("listen", params=params, content=file, headers={"Content-Type": "audio/wav"})
            response.raise_for_status()
            payload = response.json()
        alternative = payload["results"]["channels"][0]["alternatives"][0]
        segments = [
            {
                "start": row.get("start", 0),
                "end": row.get("end", 0),
                "text": row.get("transcript", ""),
                "speaker": f"spk_{row['speaker']}" if row.get("speaker") is not None else None,
            }
            for row in payload.get("results", {}).get("utterances", [])
        ]
        return {"text": alternative.get("transcript", ""), "segments": segments}

    def assemblyai(candidate):
        options = dict((candidate.get("capabilities") or {}).get("options", {}))
        with provider_client(candidate, timeout=600) as client, Path(path).open("rb") as file:
            upload = client.post("upload", content=file, headers={"Content-Type": "application/octet-stream"})
            upload.raise_for_status()
            upload_url = upload.json().get("upload_url")
            if not isinstance(upload_url, str) or not upload_url:
                raise ValueError("AssemblyAI did not return an upload URL")
            body = {
                "audio_url": upload_url,
                "speech_models": [candidate["model"]],
                "speaker_labels": diarize,
                "language_detection": language == "auto",
                **options,
            }
            if language != "auto":
                body["language_code"] = language
            if vocabulary:
                body.setdefault("word_boost", vocabulary)
                body.setdefault("boost_param", "high")
            submitted = client.post("transcript", json=body)
            submitted.raise_for_status()
            transcript_id = submitted.json().get("id")
            if not isinstance(transcript_id, str) or not transcript_id:
                raise ValueError("AssemblyAI did not return a transcript ID")
            deadline = time.monotonic() + 600
            while True:
                response = client.get("transcript/" + transcript_id)
                response.raise_for_status()
                result = response.json()
                if result.get("status") == "completed":
                    break
                if result.get("status") == "error":
                    raise ValueError("AssemblyAI transcription failed: " + str(result.get("error", "unknown error")))
                if time.monotonic() >= deadline:
                    raise TimeoutError("AssemblyAI transcription timed out")
                time.sleep(3)
        return {
            "text": result.get("text", ""),
            "segments": [
                {
                    "start": float(row.get("start", 0)) / 1000,
                    "end": float(row.get("end", 0)) / 1000,
                    "text": row.get("text", ""),
                    "speaker": f"spk_{row['speaker']}" if row.get("speaker") is not None else None,
                }
                for row in result.get("utterances", [])
            ],
        }

    def gemini(candidate):
        options = dict((candidate.get("capabilities") or {}).get("options", {}))
        generation_config = dict(options.pop("generation_config", {}))
        transcription = dict(generation_config.pop("transcription_config", options.pop("transcription_config", {})))
        # Preserve configurations written for Ollomi's early Gemini adapter.
        if "audioTranscriptionConfig" in options:
            transcription = {**dict(options.pop("audioTranscriptionConfig")), **transcription}
        if "customVocabulary" in transcription:
            transcription["custom_vocabulary"] = transcription.pop("customVocabulary")
        if language != "auto":
            transcription["language_codes"] = [language]
        # Gemini rejects custom_vocabulary together with diarization, so the
        # user's vocabulary only applies to non-diarized transcription.
        if vocabulary and not diarize and not transcription.get("custom_vocabulary"):
            transcription["custom_vocabulary"] = list(vocabulary)
        if diarize:
            if transcription.get("custom_vocabulary"):
                raise ValueError("Gemini cannot combine custom_vocabulary with diarization")
            mode = transcription.get("mode", {})
            if isinstance(mode, str):
                if mode == "smart":
                    raise ValueError("Gemini smart mode cannot combine with diarization")
                raise ValueError("Gemini transcription mode is invalid")
            if not isinstance(mode, dict):
                raise ValueError("Gemini transcription mode is invalid")
            transcription["mode"] = {"type": "verbatim", **mode, "diarization_mode": "speaker"}
        with provider_client(candidate, timeout=600) as client, Path(path).open("rb") as file:
            uploaded = client.post(
                "upload/v1beta/files",
                content=file,
                headers={
                    "Content-Type": "audio/wav",
                    "X-Goog-Upload-Protocol": "raw",
                    "X-Goog-Upload-File-Name": "audio.wav",
                },
            )
            uploaded.raise_for_status()
            file_uri = uploaded.json().get("file", {}).get("uri")
            if not isinstance(file_uri, str) or not file_uri:
                raise ValueError("Gemini did not return an uploaded file URI")
            try:
                response = client.post(
                    "v1beta/interactions",
                    json={
                        "model": candidate["model"],
                        "input": [{"type": "audio", "uri": file_uri, "mime_type": "audio/wav"}],
                        "generation_config": {"transcription_config": transcription, **generation_config},
                        **options,
                    },
                )
                response.raise_for_status()
                result = response.json()
            finally:
                uploaded_uri = urlsplit(file_uri)
                provider_uri = urlsplit(candidate["base_url"])
                if (
                    uploaded_uri.scheme == provider_uri.scheme
                    and uploaded_uri.netloc == provider_uri.netloc
                    and uploaded_uri.path.startswith("/v1beta/files/")
                ):
                    try:
                        client.delete(uploaded_uri.path.lstrip("/"))
                    except Exception:
                        # A successful transcription must not become a failed job because a provider's cleanup failed.
                        pass
        words = []
        for step in result.get("steps", []):
            for content in step.get("content", []):
                for annotation in content.get("annotations", []):
                    if annotation.get("type") != "word_info" or not isinstance(annotation.get("text"), str):
                        continue
                    try:
                        start = float(str(annotation.get("start_offset", "0")).removesuffix("s"))
                        end = float(str(annotation.get("end_offset", start)).removesuffix("s"))
                    except ValueError:
                        continue
                    words.append(
                        {
                            "start": start,
                            "end": end,
                            "text": annotation["text"],
                            "speaker": annotation.get("speaker"),
                        }
                    )
        segments = []
        for word in words:
            if segments and segments[-1]["speaker"] == word["speaker"] and word["start"] <= segments[-1]["end"] + 2:
                segments[-1]["end"] = word["end"]
                segments[-1]["text"] += " " + word["text"]
            else:
                segments.append(word)
        return {"text": result.get("output_text", ""), "segments": segments or None}

    def request(candidate):
        provider = (candidate.get("capabilities") or {}).get("provider", "custom").lower()
        if provider == "deepgram":
            result = deepgram(candidate)
        elif provider == "assemblyai":
            result = assemblyai(candidate)
        elif provider == "gemini":
            result = gemini(candidate)
        else:
            result = openai_compatible(candidate)
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
    segments = filter_silent_hallucinations(segments, path, settings().stt_silence_rms, vocabulary=vocabulary)
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
    if codec not in {"pcm16", "pcm8", "opus", "lc3_fs1030"}:
        await socket.close(code=4400, reason="Supported codecs: pcm16, pcm8, opus, lc3_fs1030")
        return
    try:
        rate = int(socket.query_params.get("sample_rate", "16000"))
    except ValueError:
        await socket.close(code=4400, reason="Invalid sample rate")
        return
    if rate not in {8000, 16000, 24000, 48000}:
        await socket.close(code=4400, reason="Unsupported sample rate")
        return
    if codec == "lc3_fs1030" and rate != 16000:
        await socket.close(code=4400, reason="Friend Pendant LC3 requires 16000 Hz")
        return
    try:
        # Seconds of silence after which a continual stream is split into a new
        # conversation. 0 disables automatic splitting (manual "split" only).
        conversation_timeout = int(socket.query_params.get("conversation_timeout", "0"))
    except ValueError:
        conversation_timeout = 0
    await socket.accept()
    # Keep device provenance on the conversation created by this socket.
    source = socket.query_params.get("source", "phone")
    if source not in {
        "omi",
        "friend_com",
        "openglass",
        "phone",
        "fieldy",
        "bee",
        "plaud",
        "apple_watch",
        "limitless",
        "rayban_meta",
    }:
        source = "phone"
    initial_conversation_id = (
        socket.query_params.get("conversation_id") or socket.query_params.get("client_conversation_id") or ident()
    )

    def prepare_conversation(conversation_id):
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
                        data=conversation_data({"status": "in_progress", "source": source}),
                    )
                )
            return selected_profile(db, user.id, "stt")

    try:
        profile = await run_in_threadpool(prepare_conversation, initial_conversation_id)
        vocabulary = [
            word
            for word in ((user.preferences or {}).get("vocabulary") or [])
            if isinstance(word, str) and word.strip()
        ]
    except HTTPException:
        await socket.close(code=4404)
        return
    decoder = None
    if codec == "opus":
        import opuslib

        decoder = opuslib.Decoder(rate, 1)
    elif codec == "lc3_fs1030":
        from selfhost.lc3_audio import Lc3Decoder

        decoder = Lc3Decoder()
    send_lock = asyncio.Lock()

    async def send_json(payload):
        async with send_lock:
            await socket.send_json(payload)

    async def send_status(status, **details):
        await send_json(
            {
                "type": "service_status",
                "status": status,
                "source": source,
                **details,
            }
        )

    class Segment:
        """One conversation captured within a long-lived listen socket.

        A continuous capture keeps the socket open and rolls the segment over on
        a manual ``split`` control frame or after ``conversation_timeout``
        seconds without speech, so the previous segment becomes its own durable
        conversation while audio continues into the next one.
        """

        def __init__(self, conversation_id):
            self.conversation_id = conversation_id
            self.file_id = ident()
            self.path = storage_path(user.id, self.file_id)
            self.wav = None
            self.total_samples = 0
            self.preview_samples = 0
            self.buffer = bytearray()
            self.last_audio_status_at = 0.0

        def open(self):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.wav = wave.open(str(self.path), "wb")
            self.wav.setnchannels(1)
            self.wav.setsampwidth(2)
            self.wav.setframerate(rate)

        def close_wav(self):
            if self.wav is not None:
                self.wav.close()
                self.wav = None

    preview_queue = asyncio.Queue(maxsize=2)
    current = Segment(initial_conversation_id)
    current.open()

    async def preview_worker():
        while True:
            pcm, offset, segment_path = await preview_queue.get()
            preview = segment_path.with_suffix(".preview.wav")

            def preview_transcript():
                with wave.open(str(preview), "wb") as clip:
                    clip.setnchannels(1)
                    clip.setsampwidth(2)
                    clip.setframerate(rate)
                    clip.writeframes(pcm)
                return transcribe_file(profile, preview, diarize=False, vocabulary=vocabulary)

            try:
                await send_status("transcribing")
                segments = await run_in_threadpool(preview_transcript)
                for segment in segments:
                    segment["start"] += offset
                    segment["end"] += offset
                if segments:
                    await send_json(segments)
                else:
                    await send_status("no_speech")
            except asyncio.CancelledError:
                raise
            except Exception:
                # Live STT is advisory. The final durable job still owns the
                # transcript and can be retried independently.
                await send_status("live_stt_unavailable", retryable=True)
            finally:
                preview.unlink(missing_ok=True)
                preview_queue.task_done()

    async def close_segment(segment):
        segment.close_wav()
        if segment.total_samples:
            job = await run_in_threadpool(
                enqueue_audio,
                user.id,
                segment.file_id,
                "recording.wav",
                "auto",
                segment.conversation_id,
            )
            try:
                await send_json({"type": "processing_started", **job})
            except Exception:
                pass
        else:
            segment.path.unlink(missing_ok=True)

    async def open_segment(conversation_id):
        # A rolled-over segment is a new conversation: it must own a record
        # before enqueue_audio can attach the finished WAV to it.
        await run_in_threadpool(prepare_conversation, conversation_id)
        segment = Segment(conversation_id)
        await run_in_threadpool(segment.open)
        return segment

    await send_json({"type": "last_memory", "memory_id": current.conversation_id})
    await send_status("ready")
    last_speech_at = time.monotonic()

    async def split(reason):
        nonlocal current, last_speech_at
        previous = current
        current = await open_segment(ident())
        last_speech_at = time.monotonic()
        await close_segment(previous)
        await send_json(
            {
                "type": "conversation_split",
                "reason": reason,
                "conversation_id": current.conversation_id,
                "memory_id": current.conversation_id,
            }
        )

    try:
        async with asyncio.TaskGroup() as tasks:
            preview_task = tasks.create_task(preview_worker(), name=f"ollomi-live-preview:{initial_conversation_id}")
            try:
                while True:
                    message = await asyncio.wait_for(socket.receive(), timeout=90)
                    if message["type"] == "websocket.disconnect":
                        break
                    if message.get("text"):
                        kind = json.loads(message["text"]).get("type")
                        if kind in {"stop", "finish"}:
                            break
                        if kind == "split":
                            await split("manual")
                            continue
                        continue
                    chunk = message.get("bytes", b"")
                    if codec == "lc3_fs1030":
                        chunk = decoder.decode(chunk)
                    elif decoder:
                        chunk = decoder.decode(chunk, rate * 120 // 1000)
                    if codec == "pcm8":
                        import audioop

                        chunk = audioop.lin2lin(audioop.bias(chunk, 1, -128), 1, 2)
                    if len(chunk) % 2:
                        raise ValueError("Unaligned PCM16")
                    current_time = time.monotonic()
                    if chunk:
                        import audioop

                        if audioop.rms(chunk, 2) > settings().stt_silence_rms:
                            last_speech_at = current_time
                        if (
                            conversation_timeout > 0
                            and current.total_samples > 0
                            and current_time - last_speech_at >= conversation_timeout
                        ):
                            await split("timeout")
                            current_time = time.monotonic()
                    current.total_samples += len(chunk) // 2
                    if current.total_samples > rate * settings().max_audio_seconds:
                        break
                    await run_in_threadpool(current.wav.writeframes, chunk)
                    current.buffer.extend(chunk)

                    if current_time - current.last_audio_status_at >= 1:
                        import audioop

                        audio_level = min(1.0, audioop.rms(chunk, 2) / 32768) if chunk else 0.0
                        await send_status("audio_received", audio_level=round(audio_level, 4))
                        current.last_audio_status_at = current_time

                    window_size = rate * 2 * 8
                    while len(current.buffer) >= window_size:
                        pcm = bytes(current.buffer[:window_size])
                        del current.buffer[:window_size]
                        offset = current.preview_samples / rate
                        current.preview_samples += window_size // 2
                        try:
                            preview_queue.put_nowait((pcm, offset, current.path))
                        except asyncio.QueueFull:
                            # Only the live preview is skipped. The WAV has
                            # already received these samples above.
                            await send_status("transcription_delayed", retryable=True)
            finally:
                preview_task.cancel()
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception:
        try:
            await send_json(
                {
                    "type": "error",
                    "message": "Live transcription interrupted; recorded audio will be processed",
                }
            )
        except Exception:
            pass
    finally:
        await close_segment(current)
