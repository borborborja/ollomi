import math
import struct
import wave

from selfhost.stt_filter import (
    filter_silent_hallucinations,
    is_hallucination,
    normalize_text,
    pcm_rms,
)


def _write_wav(path, *, seconds, amplitude, rate=16000, channels=1):
    frames = bytearray()
    samples = int(seconds * rate)
    for index in range(samples):
        value = int(amplitude * math.sin(2 * math.pi * 220 * index / rate)) if amplitude else 0
        for _ in range(channels):
            frames += struct.pack("<h", value)
    with wave.open(str(path), "wb") as clip:
        clip.setnchannels(channels)
        clip.setsampwidth(2)
        clip.setframerate(rate)
        clip.writeframes(bytes(frames))


def test_normalize_and_detect_silence_artefacts():
    assert normalize_text("  Thank you.  ") == "thank you"
    assert is_hallucination("You")
    assert is_hallucination("you")
    assert is_hallucination("[Music]")
    assert not is_hallucination("hello")
    assert not is_hallucination("you are right")


def test_repeated_silence_token_is_detected():
    assert is_hallucination("you you you")
    assert is_hallucination("Thank you. Thank you.")
    assert is_hallucination("okay okay")
    assert not is_hallucination("you and me")


def test_pcm_rms_is_zero_for_silence():
    assert pcm_rms(bytes(320)) == 0.0


def test_silent_hallucination_is_dropped(tmp_path):
    path = tmp_path / "silence.wav"
    _write_wav(path, seconds=1, amplitude=0)
    segments = [{"start": 0, "end": 1, "text": "you", "speaker": None}]
    assert filter_silent_hallucinations(segments, path, 60) == []


def test_loud_hallucination_is_kept(tmp_path):
    path = tmp_path / "loud.wav"
    _write_wav(path, seconds=1, amplitude=12000)
    segments = [{"start": 0, "end": 1, "text": "you", "speaker": None}]
    kept = filter_silent_hallucinations(segments, path, 60)
    assert [s["text"] for s in kept] == ["you"]


def test_silent_real_word_is_kept(tmp_path):
    path = tmp_path / "silence.wav"
    _write_wav(path, seconds=1, amplitude=0)
    segments = [{"start": 0, "end": 1, "text": "hola", "speaker": None}]
    kept = filter_silent_hallucinations(segments, path, 60)
    assert [s["text"] for s in kept] == ["hola"]


def test_only_the_silent_hallucination_of_a_mix_is_dropped(tmp_path):
    path = tmp_path / "mix.wav"
    _write_wav(path, seconds=2, amplitude=0)
    # Rewrite the second half with a tone so the first second stays silent.
    with wave.open(str(path), "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(16000)
        frames = bytearray(16000 * 2)  # first second silent
        for index in range(16000):
            frames += struct.pack("<h", int(12000 * math.sin(2 * math.pi * 220 * index / 16000)))
        clip.writeframes(bytes(frames))
    segments = [
        {"start": 0, "end": 1, "text": "you", "speaker": None},
        {"start": 1, "end": 2, "text": "you", "speaker": None},
    ]
    kept = filter_silent_hallucinations(segments, path, 60)
    assert [s["start"] for s in kept] == [1]


def test_unreadable_file_is_returned_unchanged(tmp_path):
    path = tmp_path / "audio.mp3"
    path.write_bytes(b"not a wave file")
    segments = [{"start": 0, "end": 1, "text": "you", "speaker": None}]
    assert filter_silent_hallucinations(segments, path, 60) == segments
