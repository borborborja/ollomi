"""Local-only speech service. Model loading never downloads files at runtime."""

import os
import shutil
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

app = FastAPI(title="Ollomi local speech")
inference_lock = threading.Lock()


def model_path(name):
    root = Path("/models").resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_dir():
        raise HTTPException(503, "Model is not installed under /models")
    return path


@lru_cache(maxsize=1)
def whisper(name):
    from faster_whisper import WhisperModel

    return WhisperModel(
        str(model_path(name)),
        device=os.getenv("WHISPER_DEVICE", "cpu"),
        compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        local_files_only=True,
    )


@lru_cache(maxsize=1)
def diarizer():
    path = Path(os.getenv("DIARIZATION_PATH", "/models/community-1"))
    if not path.is_dir():
        return None
    from pyannote.audio import Pipeline
    import torch

    pipeline = Pipeline.from_pretrained(str(path))
    pipeline.to(torch.device(os.getenv("WHISPER_DEVICE", "cpu")))
    return pipeline


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_installed": (
            Path("/models") / os.getenv("WHISPER_MODEL", "small")
        ).is_dir(),
        "diarization_installed": Path(
            os.getenv("DIARIZATION_PATH", "/models/community-1")
        ).is_dir(),
    }


@app.post("/v1/audio/transcriptions")
def transcribe(
    file: UploadFile = File(...),
    model: str = Form("small"),
    language: str | None = Form(None),
    response_format: str = Form("verbose_json"),
    diarize: bool = Form(True),
):
    with tempfile.TemporaryDirectory(prefix="speech-") as temporary:
        path = Path(temporary) / "audio"
        with path.open("wb") as output:
            shutil.copyfileobj(file.file, output, length=1024 * 1024)
        try:
            with inference_lock:
                iterator, info = whisper(model).transcribe(
                    str(path),
                    language=language,
                    vad_filter=True,
                    word_timestamps=True,
                    beam_size=5,
                )
                segments = [
                    {
                        "start": s.start,
                        "end": s.end,
                        "text": s.text,
                        "speaker": None,
                        "words": [
                            {"start": w.start, "end": w.end, "word": w.word}
                            for w in s.words or []
                        ],
                    }
                    for s in iterator
                ]
                pipeline = diarizer() if diarize and segments else None
                if pipeline is not None:
                    from faster_whisper.audio import decode_audio
                    import torch

                    waveform = torch.from_numpy(
                        decode_audio(str(path), sampling_rate=16000)
                    ).unsqueeze(0)
                    output = pipeline({"waveform": waveform, "sample_rate": 16000})
                    annotation = output.exclusive_speaker_diarization
                    turns = list(annotation.itertracks(yield_label=True))
                    for segment in segments:
                        overlaps = [
                            (
                                max(
                                    0,
                                    min(segment["end"], turn.end)
                                    - max(segment["start"], turn.start),
                                ),
                                speaker,
                            )
                            for turn, _, speaker in turns
                        ]
                        if overlaps and max(overlaps)[0] > 0:
                            segment["speaker"] = max(overlaps)[1]
            return {
                "text": "".join(s["text"] for s in segments).strip(),
                "language": info.language,
                "segments": segments,
                "diarization": pipeline is not None,
            }
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                422, "Speech processing failed: " + type(error).__name__
            ) from None


@app.get("/v1/voices")
def voices():
    return [
        {"id": path.stem, "name": path.stem}
        for path in sorted(Path("/models/piper").glob("*.onnx"))
    ]


@app.post("/v1/audio/speech")
def synthesize(body: dict):
    import subprocess
    import wave
    from fastapi.responses import Response

    text = body.get("input")
    if not isinstance(text, str) or not 0 < len(text) <= 8000:
        raise HTTPException(422, "Speech text must contain 1–8000 characters")
    name = body.get("voice") or os.getenv("PIPER_VOICE", "es_ES-davefx-medium")
    path = Path("/models/piper") / (str(name) + ".onnx")
    if path.parent.resolve() != Path("/models/piper").resolve() or not path.is_file():
        raise HTTPException(503, "Requested Piper voice is not installed")
    from piper import PiperVoice

    with tempfile.TemporaryDirectory(prefix="piper-") as temporary, inference_lock:
        wav_path = Path(temporary) / "speech.wav"
        with wave.open(str(wav_path), "wb") as output:
            PiperVoice.load(str(path)).synthesize_wav(text, output)
        result = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(wav_path),
                "-f",
                "mp3",
                "-",
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return Response(result.stdout, media_type="audio/mpeg")
