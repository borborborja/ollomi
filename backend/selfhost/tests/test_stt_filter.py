import math
import struct
import wave

from selfhost.stt_filter import (
    filter_silent_hallucinations,
    is_hallucination,
    is_vocabulary_echo,
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


def test_vocabulary_echo_detection():
    vocabulary = ["ordis", "ElGiroscopi"]
    # Exact and glued spellings are echoes.
    assert is_vocabulary_echo("El Giroscopi", vocabulary)
    assert is_vocabulary_echo("ElGiroscopi", vocabulary)
    assert is_vocabulary_echo("ordis", vocabulary)
    # Garbled model output from the live reports ("EGIRGORSOPI").
    assert is_vocabulary_echo("EGIRGORSOPI", vocabulary)
    assert is_vocabulary_echo("Elegiroscopi.com", vocabulary)
    # Real speech that merely mentions a term is not an echo.
    assert not is_vocabulary_echo("El desastre de Bermuda es", vocabulary)
    assert not is_vocabulary_echo("hemos hablado con El Giroscopi sobre el proyecto", vocabulary)
    assert not is_vocabulary_echo("ElGiroscopi", [])


def test_quiet_vocabulary_echo_is_dropped(tmp_path):
    path = tmp_path / "silence.wav"
    _write_wav(path, seconds=1, amplitude=0)
    segments = [{"start": 0, "end": 1, "text": "EGIRGORSOPI", "speaker": None}]
    assert filter_silent_hallucinations(segments, path, 60, vocabulary=["ElGiroscopi"]) == []


def test_loud_vocabulary_mention_is_kept(tmp_path):
    # A clear, loud mention of the term must survive even though a quiet echo of
    # the same text is dropped.
    path = tmp_path / "loud.wav"
    _write_wav(path, seconds=1, amplitude=12000)
    segments = [{"start": 0, "end": 1, "text": "El Giroscopi", "speaker": None}]
    kept = filter_silent_hallucinations(segments, path, 60, vocabulary=["ElGiroscopi"])
    assert [s["text"] for s in kept] == ["El Giroscopi"]


def test_no_speech_prob_drops_confident_artefacts(tmp_path):
    # Whisper-family models return no_speech_prob per segment; when the model
    # itself reports no speech, the text is an artefact even over loud audio.
    path = tmp_path / "loud.wav"
    _write_wav(path, seconds=1, amplitude=12000)
    segments = [
        {"start": 0, "end": 1, "text": "you", "speaker": None, "no_speech_prob": 0.9},
        {"start": 0, "end": 1, "text": "EGIRGORSOPI", "speaker": None, "no_speech_prob": 0.6},
        {"start": 0, "end": 1, "text": "gracias por venir", "speaker": None, "no_speech_prob": 0.2},
    ]
    kept = filter_silent_hallucinations(segments, path, 60, vocabulary=["ElGiroscopi"])
    assert [s["text"] for s in kept] == ["gracias por venir"]


def test_segment_order_is_preserved_after_filtering(tmp_path):
    path = tmp_path / "mix.wav"
    _write_wav(path, seconds=2, amplitude=0)
    with wave.open(str(path), "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(16000)
        frames = bytearray(16000 * 2)  # first second silent
        for index in range(16000):
            frames += struct.pack("<h", int(12000 * math.sin(2 * math.pi * 220 * index / 16000)))
        clip.writeframes(bytes(frames))
    segments = [
        {"start": 0, "end": 1, "text": "EGIRGORSOPI", "speaker": None},
        {"start": 1, "end": 2, "text": "hola", "speaker": None},
        {"start": 1, "end": 2, "text": "EGIRGORSOPI", "speaker": None},
    ]
    kept = filter_silent_hallucinations(segments, path, 60, vocabulary=["ElGiroscopi"])
    assert [(s["start"], s["text"]) for s in kept] == [(1, "hola"), (1, "EGIRGORSOPI")]
