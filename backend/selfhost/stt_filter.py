"""Discard STT segments that are silence artefacts rather than speech.

Whisper-family models hallucinate a small, well-known vocabulary when a window
carries no speech: most often "you" / "Thank you", but also subscribe/bye
tails. Those segments reach the live preview and the durable transcript as if
they were real words, which is what a device that streams near-silence yields.

A segment is dropped only when both conditions hold:

* its normalized text is one of the known silence artefacts, and
* the audio it spans is below the configured RMS threshold.

Keeping the energy check means a genuinely spoken "you" (loud window) is never
removed; only the hallucination on quiet audio is.

The functions here are pure and must stay usable without the full web stack so
they can be unit-tested directly.
"""

from __future__ import annotations

import audioop
import wave
from typing import Mapping, Sequence

# Silence artefacts seen from Whisper/faster-whisper when no speech is present.
HALLUCINATION_PHRASES = frozenset(
    {
        "you",
        "thank you",
        "thanks",
        "thank you very much",
        "thanks for watching",
        "thank you for watching",
        "please subscribe",
        "subscribe",
        "bye",
        "bye bye",
        "okay",
        "ok",
        "uh",
        "um",
        "hmm",
        "mm",
        "music",
        "silence",
        "[music]",
        "(music)",
        "[silence]",
        "(silence)",
        "[applause]",
        "(applause)",
        "[blank_audio]",
        "(blank_audio)",
        "subtitles by",
        "amara.org",
    }
)

_PUNCTUATION = ".,!?…:;\"'«»“”‘’"

# Single tokens that, when they are the entire (possibly repeated) segment, are
# a silence artefact rather than speech. Whisper commonly emits "you you you".
_ARTEFACT_TOKENS = frozenset(
    {"you", "thank", "thanks", "bye", "okay", "ok", "uh", "um", "hmm", "mm", "music", "silence"}
)


def normalize_text(text: str) -> str:
    without_punctuation = "".join(" " if character in _PUNCTUATION else character for character in text.lower())
    return " ".join(without_punctuation.split())


def is_hallucination(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    if normalized in HALLUCINATION_PHRASES:
        return True
    words = normalized.split()
    return bool(words) and all(word in _ARTEFACT_TOKENS for word in words)


def pcm_rms(pcm: bytes) -> float:
    if len(pcm) < 2:
        return 0.0
    return float(audioop.rms(pcm, 2))


def _load_wave(path) -> tuple[int, int, int, bytes] | None:
    try:
        with wave.open(str(path), "rb") as recording:
            rate = recording.getframerate()
            width = recording.getsampwidth()
            channels = recording.getnchannels()
            frames = recording.readframes(recording.getnframes())
    except (wave.Error, OSError, EOFError, ValueError):
        return None
    if width != 2 or rate <= 0 or channels <= 0 or not frames:
        return None
    return rate, channels, len(frames), frames


def _segment_rms(frames: bytes, rate: int, channels: int, start: float, end: float) -> float:
    stride = 2 * channels
    total_frames = len(frames) // stride
    begin = max(0, min(total_frames, int(max(0.0, start) * rate)))
    stop = total_frames if end <= start else max(begin, min(total_frames, int(end * rate)))
    return pcm_rms(frames[begin * stride : stop * stride])


def filter_silent_hallucinations(
    segments: Sequence[Mapping],
    path,
    threshold: float,
) -> list[Mapping]:
    """Return `segments` without silence artefacts masked by quiet audio."""
    if not segments:
        return list(segments)
    if not any(is_hallucination(str(segment.get("text", ""))) for segment in segments):
        return list(segments)
    loaded = _load_wave(path)
    if loaded is None:
        return list(segments)
    rate, channels, total_frames, frames = loaded
    duration = total_frames / rate
    kept: list[Mapping] = []
    for segment in segments:
        if not is_hallucination(str(segment.get("text", ""))):
            kept.append(segment)
            continue
        try:
            start = float(segment.get("start", 0) or 0)
            end = float(segment.get("end", 0) or 0)
        except (TypeError, ValueError):
            start, end = 0.0, duration
        if end <= start:
            start, end = 0.0, duration
        if _segment_rms(frames, rate, channels, start, end) > threshold:
            kept.append(segment)
    return kept
