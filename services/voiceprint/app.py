"""Minimal authenticated speaker-embedding service for Ollomi.

It is intentionally independent from the main Compose stack: run it on a CPU
host that can keep the ECAPA model cached, and expose it only to Ollomi over a
private network or HTTPS reverse proxy.
"""

import io
import math
import os
from contextlib import asynccontextmanager

import torch
import torchaudio
from fastapi import FastAPI, File, HTTPException, Request, UploadFile

# The release image bakes a reviewed ECAPA revision into this local path. A
# deployment may point at another *local* mounted model directory, but it must
# not turn a runtime health check into a Hugging Face download.
MODEL_SOURCE = os.getenv("VOICEPRINT_MODEL", "/opt/ollomi-voiceprint-model")
MODEL_DIR = os.getenv("VOICEPRINT_MODEL_DIR", "/tmp/ollomi-voiceprint-runtime")
API_KEY = os.getenv("VOICEPRINT_API_KEY", "")
MAX_UPLOAD_BYTES = 24 * 1024 * 1024
MIN_SECONDS = 1.5
MAX_DIARIZATION_SECONDS = float(os.getenv("VOICEPRINT_MAX_DIARIZATION_SECONDS", "150"))
DIARIZATION_WINDOW_SECONDS = float(os.getenv("VOICEPRINT_DIARIZATION_WINDOW_SECONDS", "3"))
DIARIZATION_STEP_SECONDS = float(os.getenv("VOICEPRINT_DIARIZATION_STEP_SECONDS", "1.5"))
DIARIZATION_THRESHOLD = float(os.getenv("VOICEPRINT_DIARIZATION_THRESHOLD", "0.68"))
MAX_SPEAKERS = int(os.getenv("VOICEPRINT_MAX_SPEAKERS", "8"))
_classifier = None


def classifier():
    global _classifier
    if _classifier is None:
        from speechbrain.inference.speaker import EncoderClassifier

        _classifier = EncoderClassifier.from_hparams(
            source=MODEL_SOURCE,
            savedir=MODEL_DIR,
            run_opts={"device": "cpu"},
        )
    return _classifier


def load_waveform(content):
    try:
        waveform, sample_rate = torchaudio.load(io.BytesIO(content))
    except Exception as error:  # decoder errors have many implementation-specific types
        raise HTTPException(422, "Unsupported or corrupt audio") from error
    if waveform.numel() == 0:
        raise HTTPException(422, "Audio is empty")
    waveform = waveform.mean(dim=0, keepdim=True)
    if sample_rate != 16000:
        waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
    return waveform


def normalized_embedding(waveform):
    if waveform.shape[1] < int(16000 * MIN_SECONDS):
        raise HTTPException(422, "Voice sample must contain at least 1.5 seconds of speech")
    with torch.inference_mode():
        vector = classifier().encode_batch(waveform).squeeze().float()
        vector = vector / torch.linalg.vector_norm(vector)
    values = vector.tolist()
    if not values or not all(math.isfinite(value) for value in values):
        raise HTTPException(502, "Model produced an invalid embedding")
    return values


def embedding(content):
    return normalized_embedding(load_waveform(content))


def _validate_diarization_settings():
    if not 1.5 <= DIARIZATION_WINDOW_SECONDS <= 10:
        raise HTTPException(503, "VOICEPRINT_DIARIZATION_WINDOW_SECONDS must be between 1.5 and 10")
    if not 0.5 <= DIARIZATION_STEP_SECONDS <= DIARIZATION_WINDOW_SECONDS:
        raise HTTPException(503, "VOICEPRINT_DIARIZATION_STEP_SECONDS is invalid")
    if not 0.5 <= DIARIZATION_THRESHOLD <= 0.95:
        raise HTTPException(503, "VOICEPRINT_DIARIZATION_THRESHOLD must be between 0.5 and 0.95")
    if not 1 <= MAX_SPEAKERS <= 16:
        raise HTTPException(503, "VOICEPRINT_MAX_SPEAKERS must be between 1 and 16")


def _speech_windows(waveform):
    """Return short speech-bearing windows without retaining the recording.

    ECAPA produces speaker embeddings, not a turn detector.  An energy gate
    plus overlapping windows is intentionally conservative: it avoids making
    silence a speaker, while a caller can still retain provider diarization
    when it is available.
    """
    _validate_diarization_settings()
    rate = 16000
    frame_count = waveform.shape[1]
    if frame_count / rate > MAX_DIARIZATION_SECONDS:
        raise HTTPException(422, "Audio exceeds the diarization duration limit")
    window = int(DIARIZATION_WINDOW_SECONDS * rate)
    step = int(DIARIZATION_STEP_SECONDS * rate)
    if frame_count < window:
        return []
    candidates = []
    for start in range(0, frame_count - window + 1, step):
        clip = waveform[:, start : start + window]
        candidates.append((start, clip, float(torch.sqrt(torch.mean(clip.square())).item())))
    if not candidates:
        return []
    maximum = max(item[2] for item in candidates)
    if maximum < 0.00001:
        return []
    # The threshold adapts to quiet recordings while rejecting background
    # silence in an otherwise loud one.
    minimum = maximum * 0.12
    return [(start, clip) for start, clip, energy in candidates if energy >= minimum]


def _window_embeddings(windows):
    if not windows:
        return []
    batches = []
    for index in range(0, len(windows), 16):
        batch = torch.cat([clip for _start, clip in windows[index : index + 16]], dim=0)
        with torch.inference_mode():
            vectors = classifier().encode_batch(batch).squeeze(1).float()
            vectors = vectors / torch.linalg.vector_norm(vectors, dim=1, keepdim=True)
        batches.extend(vectors.cpu())
    return batches


def _speaker_labels(vectors):
    centers, counts, labels = [], [], []
    for vector in vectors:
        if centers:
            similarities = [float(torch.dot(vector, center).item()) for center in centers]
            best = max(range(len(similarities)), key=similarities.__getitem__)
        else:
            similarities, best = [], None
        if best is None or (similarities[best] < DIARIZATION_THRESHOLD and len(centers) < MAX_SPEAKERS):
            centers.append(vector.clone())
            counts.append(1)
            labels.append(len(centers) - 1)
            continue
        labels.append(best)
        counts[best] += 1
        center = centers[best] * (counts[best] - 1) + vector
        centers[best] = center / torch.linalg.vector_norm(center)
    return labels


def diarize(content):
    waveform = load_waveform(content)
    windows = _speech_windows(waveform)
    if not windows:
        return []
    labels = _speaker_labels(_window_embeddings(windows))
    duration = waveform.shape[1] / 16000
    centers = [(start / 16000) + DIARIZATION_WINDOW_SECONDS / 2 for start, _clip in windows]
    turns = []
    for index, label in enumerate(labels):
        start = 0.0 if index == 0 else (centers[index - 1] + centers[index]) / 2
        end = duration if index == len(labels) - 1 else (centers[index] + centers[index + 1]) / 2
        speaker = f"spk_{label}"
        if turns and turns[-1]["speaker"] == speaker and start - turns[-1]["end"] <= DIARIZATION_STEP_SECONDS:
            turns[-1]["end"] = end
        else:
            turns.append({"start": round(start, 3), "end": round(end, 3), "speaker": speaker})
    return turns


def authorize(request):
    if not API_KEY:
        raise HTTPException(503, "VOICEPRINT_API_KEY is not configured")
    if request.headers.get("authorization") != f"Bearer {API_KEY}":
        raise HTTPException(401, "Invalid API key", headers={"WWW-Authenticate": "Bearer"})


@asynccontextmanager
async def lifespan(_app):
    # Load/download before advertising readiness. This makes restarts and model
    # cache failures visible to the orchestrator rather than first enrollment.
    classifier()
    yield


app = FastAPI(title="Ollomi Voiceprint", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_SOURCE, "diarization": "ecapa-energy-clustering"}


@app.post("/v1/embeddings")
async def embeddings(request: Request, file: UploadFile = File(...)):
    authorize(request)
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Audio exceeds 24 MiB")
        return {"embedding": embedding(content)}
    finally:
        await file.close()


@app.post("/v1/diarize")
async def diarize_audio(request: Request, file: UploadFile = File(...)):
    authorize(request)
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Audio exceeds 24 MiB")
        return {"segments": diarize(content), "retains_audio": False}
    finally:
        await file.close()
