"""Discard STT segments that are silence artefacts rather than speech.

Whisper-family models hallucinate a small, well-known vocabulary when a window
carries no speech: most often "you" / "Thank you", but also subscribe/bye
tails. Those segments reach the live preview and the durable transcript as if
they were real words, which is what a device that streams near-silence yields.

A second artefact class is provider biasing: when a model is given the user's
custom vocabulary as a prompt (or through a native keyword API), audio without
speech can come back as the vocabulary itself, usually garbled — "ElGiroscopi"
returns as "EGIRGORSOPI" or "Elegiroscopi.com". Those segments are matched
fuzzily against the vocabulary and dropped when the model itself reports no
speech (`no_speech_prob`) or the window is quiet.

A segment is dropped only when a positive signal says it is not speech:

* its `no_speech_prob` is at/above [NO_SPEECH_PROB_DROP],
* its normalized text is one of the known silence artefacts and the audio it
  spans is below the configured RMS threshold,
* it is a vocabulary echo with `no_speech_prob` at/above
  [VOCABULARY_ECHO_NO_SPEECH_PROB], or one whose audio is below the threshold.

Keeping the energy/confidence checks means a genuinely spoken "you" or a real
mention of a vocabulary term in clear audio is never removed; only the
hallucination on quiet or uncertain audio is.

The functions here are pure and must stay usable without the full web stack so
they can be unit-tested directly.
"""

from __future__ import annotations

import audioop
import wave
from difflib import SequenceMatcher
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

# The model itself reports it heard no speech: drop the segment regardless of
# its text (Whisper emits its most confident artefacts there).
NO_SPEECH_PROB_DROP = 0.8

# A vocabulary-only segment is uncertain enough to drop when the model is at
# least this doubtful about speech, even if the window carries energy (music,
# noise) where the energy check alone would keep it.
VOCABULARY_ECHO_NO_SPEECH_PROB = 0.5

# Similarity ratio between the whole normalized segment and a vocabulary term
# above which a garbled echo ("EGIRGORSOPI" for "ElGiroscopi") is recognized.
VOCABULARY_MATCH_RATIO = 0.7


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


def is_vocabulary_echo(text: str, vocabulary: Sequence[str]) -> bool:
    """True when the segment is only the custom vocabulary echoed back.

    Provider biasing can make a model emit the given terms on audio with no
    speech, frequently garbled, so the whole normalized segment is compared
    against each normalized term with a similarity ratio. A longer segment that
    merely mentions a term keeps a low ratio and survives.
    """
    normalized = normalize_text(text).replace(" ", "")
    if not normalized or not vocabulary:
        return False
    for term in vocabulary:
        candidate = normalize_text(str(term)).replace(" ", "")
        if candidate and SequenceMatcher(None, normalized, candidate).ratio() >= VOCABULARY_MATCH_RATIO:
            return True
    return False


def _no_speech_prob(segment: Mapping) -> float | None:
    try:
        return float(segment.get("no_speech_prob"))
    except (TypeError, ValueError):
        return None


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
    vocabulary: Sequence[str] = (),
) -> list[Mapping]:
    """Return `segments` without silence artefacts masked by quiet audio."""
    if not segments:
        return list(segments)
    verdicts: list[bool] = []
    energy_checked: list[int] = []
    for index, segment in enumerate(segments):
        text = str(segment.get("text", ""))
        no_speech = _no_speech_prob(segment)
        if no_speech is not None and no_speech >= NO_SPEECH_PROB_DROP:
            verdicts.append(False)
            continue
        artefact = is_hallucination(text)
        echo = is_vocabulary_echo(text, vocabulary)
        if echo and no_speech is not None and no_speech >= VOCABULARY_ECHO_NO_SPEECH_PROB:
            verdicts.append(False)
            continue
        # Provisional keep: an artefact/echo still survives if its window is loud
        # enough to be speech (the energy check below decides).
        verdicts.append(True)
        if artefact or echo:
            energy_checked.append(index)
    if not energy_checked:
        return [segment for segment, keep in zip(segments, verdicts) if keep]
    loaded = _load_wave(path)
    if loaded is None:
        return list(segments)
    rate, channels, total_frames, frames = loaded
    duration = total_frames / rate
    for index in energy_checked:
        segment = segments[index]
        try:
            start = float(segment.get("start", 0) or 0)
            end = float(segment.get("end", 0) or 0)
        except (TypeError, ValueError):
            start, end = 0.0, duration
        if end <= start:
            start, end = 0.0, duration
        if _segment_rms(frames, rate, channels, start, end) <= threshold:
            verdicts[index] = False
    return [segment for segment, keep in zip(segments, verdicts) if keep]
