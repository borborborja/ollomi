from contextlib import nullcontext
from unittest.mock import ANY


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_deepgram_adapter_preserves_speaker_segments(tmp_path, monkeypatch):
    from selfhost import audio

    calls = []

    class Client:
        def post(self, endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            return Response(
                {
                    "results": {
                        "channels": [{"alternatives": [{"transcript": "Bon dia"}]}],
                        "utterances": [{"start": 0.0, "end": 0.8, "transcript": "Bon dia", "speaker": 1}],
                    }
                }
            )

    monkeypatch.setattr(audio, "provider_client", lambda *args, **kwargs: nullcontext(Client()))
    path = tmp_path / "audio.wav"
    path.write_bytes(b"not-used-by-the-fake")
    profile = {"purpose": "stt", "model": "nova-3", "capabilities": {"provider": "deepgram"}}

    assert audio.transcribe_file(profile, path) == [
        {
            "id": ANY,
            "start": 0.0,
            "end": 0.8,
            "text": "Bon dia",
            "speaker": "spk_1",
            "is_user": False,
            "person_id": None,
            "translations": [],
        }
    ]
    assert calls[0][0] == "listen"
    assert calls[0][1]["params"]["diarize"] == "true"


def test_gemini_adapter_uses_interactions_and_preserves_speaker_turns(tmp_path, monkeypatch):
    from selfhost import audio

    calls = []

    class Client:
        def post(self, endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            if endpoint == "upload/v1beta/files":
                return Response({"file": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/audio-1"}})
            return Response(
                {
                    "output_text": "Bon dia",
                    "steps": [
                        {
                            "content": [
                                {
                                    "annotations": [
                                        {
                                            "type": "word_info",
                                            "text": "Bon",
                                            "speaker": "spk_1",
                                            "start_offset": "0.100s",
                                            "end_offset": "0.300s",
                                        },
                                        {
                                            "type": "word_info",
                                            "text": "dia",
                                            "speaker": "spk_1",
                                            "start_offset": "0.350s",
                                            "end_offset": "0.600s",
                                        },
                                    ]
                                }
                            ]
                        }
                    ],
                }
            )

        def delete(self, endpoint):
            calls.append(("DELETE " + endpoint, {}))
            return Response({})

    monkeypatch.setattr(audio, "provider_client", lambda *args, **kwargs: nullcontext(Client()))
    path = tmp_path / "audio.wav"
    path.write_bytes(b"not-used-by-the-fake")
    profile = {
        "purpose": "stt",
        "model": "gemini-3.5-transcribe",
        "base_url": "https://generativelanguage.googleapis.com",
        "capabilities": {"provider": "gemini"},
    }

    result = audio.transcribe_file(profile, path, language="ca-ES")
    assert result[0]["text"] == "Bon dia"
    assert result[0]["speaker"] == "spk_1"
    assert result[0]["start"] == 0.1
    assert result[0]["end"] == 0.6
    assert calls[1][0] == "v1beta/interactions"
    assert calls[1][1]["json"]["generation_config"]["transcription_config"] == {
        "language_codes": ["ca-ES"],
        "mode": {"type": "verbatim", "diarization_mode": "speaker"},
    }


def test_native_embedding_adapters_use_their_documented_wire_shapes(monkeypatch):
    from selfhost import profiles

    calls = []

    class Client:
        def post(self, endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            if endpoint == "embed":
                return Response({"embeddings": {"float": [[0.1, 0.2]]}})
            return Response({"data": [{"index": 0, "embedding": [0.3, 0.4]}]})

    monkeypatch.setattr(profiles, "provider_client", lambda *args, **kwargs: nullcontext(Client()))
    cohere = {"purpose": "embedding", "model": "embed-v4.0", "capabilities": {"provider": "cohere"}}
    voyage = {"purpose": "embedding", "model": "voyage-4-lite", "capabilities": {"provider": "voyage"}}

    assert profiles.embed(cohere, ["document"], fallback=False, input_type="search_document") == [[0.1, 0.2]]
    assert profiles.embed(voyage, ["question"], fallback=False, input_type="search_query") == [[0.3, 0.4]]
    assert calls[0][0] == "embed"
    assert calls[0][1]["json"]["texts"] == ["document"]
    assert calls[1][0] == "embeddings"
    assert calls[1][1]["json"]["input_type"] == "query"


def _stt_response(provider):
    if provider == "deepgram":
        return {
            "results": {
                "channels": [{"alternatives": [{"transcript": "ok"}]}],
                "utterances": [],
            }
        }
    return {"text": "ok", "segments": [{"start": 0.0, "end": 1.0, "text": "ok"}]}


def test_openai_compatible_vocabulary_becomes_prompt(tmp_path, monkeypatch):
    from selfhost import audio

    calls = []

    class Client:
        def post(self, endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            return Response(_stt_response("custom"))

    monkeypatch.setattr(audio, "provider_client", lambda *args, **kwargs: nullcontext(Client()))
    path = tmp_path / "audio.wav"
    path.write_bytes(b"not-used-by-the-fake")
    profile = {"purpose": "stt", "model": "whisper-large-v3", "capabilities": {"provider": "custom"}}

    audio.transcribe_file(profile, path, vocabulary=["Ollomi", "Micapum"])

    assert calls[0][1]["data"]["prompt"] == "Ollomi, Micapum"


def test_openai_compatible_keeps_an_explicit_prompt(tmp_path, monkeypatch):
    from selfhost import audio

    calls = []

    class Client:
        def post(self, endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            return Response(_stt_response("custom"))

    monkeypatch.setattr(audio, "provider_client", lambda *args, **kwargs: nullcontext(Client()))
    path = tmp_path / "audio.wav"
    path.write_bytes(b"not-used-by-the-fake")
    profile = {
        "purpose": "stt",
        "model": "whisper-large-v3",
        "capabilities": {"provider": "custom", "options": {"prompt": "fixed"}},
    }

    audio.transcribe_file(profile, path, vocabulary=["Ollomi"])

    assert calls[0][1]["data"]["prompt"] == "fixed"


def test_deepgram_vocabulary_becomes_keywords(tmp_path, monkeypatch):
    from selfhost import audio

    calls = []

    class Client:
        def post(self, endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            return Response(_stt_response("deepgram"))

    monkeypatch.setattr(audio, "provider_client", lambda *args, **kwargs: nullcontext(Client()))
    path = tmp_path / "audio.wav"
    path.write_bytes(b"not-used-by-the-fake")
    profile = {"purpose": "stt", "model": "nova-3", "capabilities": {"provider": "deepgram"}}

    audio.transcribe_file(profile, path, vocabulary=["Ollomi"])

    assert calls[0][1]["params"]["keywords"] == ["Ollomi"]
