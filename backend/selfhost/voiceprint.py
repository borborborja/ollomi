"""Private, opt-in recognition of the account owner's voice.

The main Ollomi stack never downloads an embedding model.  It sends a short
WAV excerpt to the administrator-configured voiceprint service, keeps only an
encrypted embedding in the user's preferences, and deletes the enrollment
audio as soon as the request completes.
"""

import io
import json
import logging
import math
import re
import wave
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from selfhost.config import settings
from selfhost.db import User, emit, ident, transaction
from selfhost.security import current_user, seal, unseal

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_ENROLLMENT_BYTES = 24 * 1024 * 1024
MAX_DIARIZATION_BYTES = 24 * 1024 * 1024
MIN_SAMPLE_SECONDS = 1.5
MAX_SAMPLE_SECONDS = 45.0


class VoiceprintUnavailable(RuntimeError):
    pass


def enabled():
    return bool(settings().voiceprint_url)


def _normalize(vector):
    if not isinstance(vector, list) or not 64 <= len(vector) <= 2048:
        raise VoiceprintUnavailable("Voiceprint service returned an invalid embedding")
    try:
        values = [float(value) for value in vector]
    except (TypeError, ValueError):
        raise VoiceprintUnavailable("Voiceprint service returned a non-numeric embedding") from None
    if not all(math.isfinite(value) for value in values):
        raise VoiceprintUnavailable("Voiceprint service returned a non-finite embedding")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise VoiceprintUnavailable("Voiceprint service returned an empty embedding")
    return [value / norm for value in values]


def remote_embedding(content, filename="sample.wav", content_type="audio/wav"):
    if not enabled():
        raise VoiceprintUnavailable("Voiceprint service is not configured")
    headers = {}
    key = settings().voiceprint_api_key.get_secret_value()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        response = httpx.post(
            settings().voiceprint_url.rstrip("/") + "/v1/embeddings",
            headers=headers,
            files={"file": (Path(filename).name or "sample.wav", content, content_type)},
            timeout=90.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise VoiceprintUnavailable("Voiceprint service is unavailable") from error
    return _normalize(payload.get("embedding"))


def remote_diarization(content, filename="clip.wav", content_type="audio/wav"):
    if not enabled():
        raise VoiceprintUnavailable("Voiceprint service is not configured")
    if len(content) > MAX_DIARIZATION_BYTES:
        raise VoiceprintUnavailable("Audio clip exceeds the diarization limit")
    headers = {}
    key = settings().voiceprint_api_key.get_secret_value()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        response = httpx.post(
            settings().voiceprint_url.rstrip("/") + "/v1/diarize",
            headers=headers,
            files={"file": (Path(filename).name or "clip.wav", content, content_type)},
            timeout=120.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        rows = response.json().get("segments")
    except (httpx.HTTPError, ValueError, AttributeError) as error:
        raise VoiceprintUnavailable("Voiceprint diarization service is unavailable") from error
    if not isinstance(rows, list) or len(rows) > 1000:
        raise VoiceprintUnavailable("Voiceprint service returned invalid speaker turns")
    turns = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("speaker"), str):
            raise VoiceprintUnavailable("Voiceprint service returned an invalid speaker label")
        if not re.fullmatch(r"spk_[0-9]{1,4}", row["speaker"]):
            raise VoiceprintUnavailable("Voiceprint service returned an unsafe speaker label")
        try:
            start, end = float(row["start"]), float(row["end"])
        except (KeyError, TypeError, ValueError):
            raise VoiceprintUnavailable("Voiceprint service returned invalid speaker timings") from None
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= 150):
            raise VoiceprintUnavailable("Voiceprint service returned unsafe speaker timings")
        turns.append({"start": start, "end": end, "speaker": row["speaker"][:100]})
    turns.sort(key=lambda item: (item["start"], item["end"]))
    if any(right["start"] < left["end"] for left, right in zip(turns, turns[1:])):
        raise VoiceprintUnavailable("Voiceprint service returned overlapping speaker turns")
    return turns


def _stored_embedding(user):
    value = (user.preferences or {}).get("voiceprint_profile")
    if not value:
        return None
    try:
        return _normalize(json.loads(unseal(value)).get("embedding"))
    except Exception:  # noqa: BLE001 - an old/corrupt biometric template must not break transcription
        logger.warning("Ignoring unreadable voiceprint for user %s", user.id)
        return None


def _save_embedding(user_id, embedding):
    with transaction() as db:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(404, "User not found")
        user.preferences = {
            **(user.preferences or {}),
            "voiceprint_profile": seal(json.dumps({"embedding": embedding}, separators=(",", ":"))),
        }
        emit(db, user.id, "voiceprint_enrolled", {})


def _profile_for(user_id):
    if not enabled():
        return None
    with transaction() as db:
        user = db.get(User, user_id)
        return _stored_embedding(user) if user else None


def _speaker_sample(path, spans):
    """Return up to 45 seconds of one diarized speaker from a normalized WAV."""
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        if rate <= 0 or channels != 1 or sample_width != 2:
            raise VoiceprintUnavailable("Voiceprint expects normalized mono PCM audio")
        pieces, retained = [], 0
        limit = int(MAX_SAMPLE_SECONDS * rate)
        for start, end in spans:
            start_frame = max(0, int(float(start) * rate))
            end_frame = max(start_frame, int(float(end) * rate))
            wanted = min(end_frame - start_frame, limit - retained)
            if wanted <= 0:
                break
            source.setpos(min(start_frame, source.getnframes()))
            chunk = source.readframes(wanted)
            pieces.append(chunk)
            retained += len(chunk) // (channels * sample_width)
            if retained >= limit:
                break
    if retained < int(MIN_SAMPLE_SECONDS * rate):
        return None
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(sample_width)
        target.setframerate(rate)
        target.writeframes(b"".join(pieces))
    return output.getvalue()


def _similarity(left, right):
    if len(left) != len(right):
        raise VoiceprintUnavailable("Voiceprint model dimension changed; enroll again")
    return sum(a * b for a, b in zip(left, right))


def _word_chunks(text, weights):
    words = text.split()
    if len(weights) <= 1 or not words:
        return [text] if weights else []
    selected = len(weights)
    counts = [0] * selected
    # Do not invent text for a turn: when there are fewer words than turns,
    # assign the available words to the longest acoustic turns.
    if len(words) < selected:
        for index in sorted(range(selected), key=lambda item: weights[item], reverse=True)[: len(words)]:
            counts[index] = 1
    else:
        counts = [1] * selected
        remaining = len(words) - selected
        total = sum(weights) or float(selected)
        shares = [remaining * weight / total for weight in weights]
        extras = [int(share) for share in shares]
        counts = [count + extra for count, extra in zip(counts, extras)]
        leftover = remaining - sum(extras)
        for index in sorted(
            range(selected), key=lambda item: (shares[item] - extras[item], weights[item]), reverse=True
        )[:leftover]:
            counts[index] += 1
    cursor, chunks = 0, []
    for count in counts:
        chunks.append(" ".join(words[cursor : cursor + count]))
        cursor += count
    if cursor < len(words):
        chunks[-1] = (chunks[-1] + " " + " ".join(words[cursor:])).strip()
    return chunks


def diarize_segments(path, segments):
    """Assign local speaker labels when an STT result does not include them.

    Existing native-provider labels take precedence.  Text-only STT responses
    do not have word timings, so a multi-speaker sentence is split
    proportionally and marked by real audio turn boundaries rather than being
    falsely attributed to a single person.
    """
    if not enabled() or not any(not item.get("speaker") for item in segments):
        return segments
    try:
        content = Path(path).read_bytes()
    except OSError as error:
        raise VoiceprintUnavailable("Normalized audio is unavailable for diarization") from error
    turns = remote_diarization(content, Path(path).name)
    if not turns:
        return segments
    result = []
    for segment in segments:
        if segment.get("speaker"):
            result.append(segment)
            continue
        start, end = float(segment.get("start", 0)), float(segment.get("end", 0))
        overlaps = []
        for turn in turns:
            overlap_start, overlap_end = max(start, turn["start"]), min(end, turn["end"])
            if overlap_end > overlap_start:
                overlaps.append({**turn, "start": overlap_start, "end": overlap_end})
        if not overlaps:
            result.append(segment)
            continue
        chunks = _word_chunks(str(segment.get("text", "")), [item["end"] - item["start"] for item in overlaps])
        if not any(text.strip() for text in chunks):
            result.append(segment)
            continue
        for index, (turn, text) in enumerate(zip(overlaps, chunks)):
            if not text.strip():
                continue
            result.append(
                {
                    **segment,
                    "id": segment.get("id") if index == 0 else ident(),
                    "start": turn["start"],
                    "end": turn["end"],
                    "text": text,
                    "speaker": turn["speaker"],
                    "is_user": False,
                }
            )
    return result


def classify_segments(user_id, path, segments):
    """Set `is_user` on all matching diarized segments, without persistence."""
    template = _profile_for(user_id)
    if not template:
        return segments
    groups = {}
    for segment in segments:
        speaker = segment.get("speaker")
        if speaker:
            groups.setdefault(str(speaker), []).append((segment.get("start", 0), segment.get("end", 0)))
    for speaker, spans in groups.items():
        content = _speaker_sample(path, spans)
        if not content:
            continue
        candidate = remote_embedding(content, f"{speaker}.wav")
        if _similarity(template, candidate) >= settings().voiceprint_threshold:
            for segment in segments:
                if str(segment.get("speaker")) == speaker:
                    segment["is_user"] = True
    return segments


@router.get("/v1/speech-profile")
def speech_profile(user=Depends(current_user)):
    return {
        "available": enabled(),
        "has_profile": bool(_stored_embedding(user)),
        "retains_audio": False,
    }


@router.post("/v1/speech-profile")
async def enroll_speech_profile(file: UploadFile = File(...), user=Depends(current_user)):
    if not enabled():
        raise HTTPException(503, "Voiceprint service is not configured")
    try:
        content = await file.read(MAX_ENROLLMENT_BYTES + 1)
        if not content:
            raise HTTPException(422, "Voice sample is empty")
        if len(content) > MAX_ENROLLMENT_BYTES:
            raise HTTPException(413, "Voice sample exceeds 24 MiB")
        embedding = await run_in_threadpool(
            remote_embedding, content, file.filename or "voiceprint.wav", file.content_type or "audio/wav"
        )
        await run_in_threadpool(_save_embedding, user.id, embedding)
        return {"available": True, "has_profile": True, "retains_audio": False}
    except VoiceprintUnavailable as error:
        raise HTTPException(503, str(error)) from None
    finally:
        await file.close()


@router.delete("/v1/speech-profile")
def delete_speech_profile(user=Depends(current_user)):
    with transaction() as db:
        row = db.get(User, user.id)
        preferences = dict(row.preferences or {})
        preferences.pop("voiceprint_profile", None)
        row.preferences = preferences
        emit(db, row.id, "voiceprint_deleted", {})
    return {"status": "ok"}
