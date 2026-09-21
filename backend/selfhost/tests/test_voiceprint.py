from sqlalchemy import select


def _configure(monkeypatch):
    monkeypatch.setenv("OLLOMI_VOICEPRINT_URL", "https://voiceprint.test")
    monkeypatch.setenv("OLLOMI_VOICEPRINT_API_KEY", "voiceprint-test-key")
    from selfhost.config import settings

    settings.cache_clear()


def test_enrollment_is_encrypted_and_never_returns_voice_data(client, admin, monkeypatch):
    _configure(monkeypatch)
    from selfhost import voiceprint
    from selfhost.db import User, transaction

    calls = []

    def fake_embedding(content, filename="sample.wav", content_type="audio/wav"):
        calls.append((content, filename, content_type))
        return [1.0] + [0.0] * 63

    monkeypatch.setattr(voiceprint, "remote_embedding", fake_embedding)
    capabilities = client.get("/v1/server-info").json()["capabilities"]
    assert "voiceprint" in capabilities
    assert "speaker_diarization" in capabilities
    response = client.post(
        "/v1/speech-profile",
        headers=admin,
        files={"file": ("my-voice.wav", b"not persisted", "audio/wav")},
    )
    assert response.status_code == 200
    assert response.json() == {"available": True, "has_profile": True, "retains_audio": False}
    assert calls == [(b"not persisted", "my-voice.wav", "audio/wav")]
    assert client.get("/v1/speech-profile", headers=admin).json() == response.json()
    with transaction() as db:
        user = db.scalar(select(User).where(User.email == "admin@test.local"))
        encrypted = user.preferences["voiceprint_profile"]
    assert "not persisted" not in encrypted
    assert "[1.0" not in encrypted


def test_profile_delete_and_disabled_status(client, admin, monkeypatch):
    from selfhost.config import settings

    settings.cache_clear()
    assert client.get("/v1/speech-profile", headers=admin).json() == {
        "available": False,
        "has_profile": False,
        "retains_audio": False,
    }
    assert client.post("/v1/speech-profile", headers=admin, files={"file": ("voice.wav", b"x", "audio/wav")}).status_code == 503

    _configure(monkeypatch)
    from selfhost import voiceprint

    monkeypatch.setattr(voiceprint, "remote_embedding", lambda *args: [1.0] + [0.0] * 63)
    assert client.post("/v1/speech-profile", headers=admin, files={"file": ("voice.wav", b"x", "audio/wav")}).status_code == 200
    assert client.delete("/v1/speech-profile", headers=admin).json() == {"status": "ok"}
    assert client.get("/v1/speech-profile", headers=admin).json()["has_profile"] is False


def test_classification_marks_only_matching_diarized_speaker(client, admin, monkeypatch, tmp_path):
    _configure(monkeypatch)
    from selfhost import voiceprint

    monkeypatch.setattr(voiceprint, "remote_embedding", lambda *args: [1.0] + [0.0] * 63)
    assert client.post("/v1/speech-profile", headers=admin, files={"file": ("voice.wav", b"x", "audio/wav")}).status_code == 200
    account_id = client.get("/v1/auth/me", headers=admin).json()["uid"]

    monkeypatch.setattr(
        voiceprint,
        "remote_embedding",
        lambda content, *args: ([1.0] + [0.0] * 63 if content == b"me" else [0.0, 1.0] + [0.0] * 62),
    )
    monkeypatch.setattr(voiceprint, "_speaker_sample", lambda _path, spans: b"me" if spans[0][0] == 0 else b"other")
    segments = [
        {"speaker": "spk_me", "start": 0, "end": 3, "text": "me", "is_user": False},
        {"speaker": "spk_other", "start": 4, "end": 7, "text": "other", "is_user": False},
    ]
    assert voiceprint.classify_segments(account_id, tmp_path / "normalized.wav", segments) == segments
    assert [item["is_user"] for item in segments] == [True, False]


def test_local_diarization_splits_text_only_transcription_without_loss(monkeypatch, tmp_path):
    _configure(monkeypatch)
    from selfhost import voiceprint

    clip = tmp_path / "normalized.wav"
    clip.write_bytes(b"temporary normalized audio")
    monkeypatch.setattr(
        voiceprint,
        "remote_diarization",
        lambda *_args: [
            {"start": 0.0, "end": 3.0, "speaker": "spk_0"},
            {"start": 3.0, "end": 6.0, "speaker": "spk_1"},
        ],
    )
    original = {
        "id": "one",
        "start": 0.0,
        "end": 6.0,
        "text": "un dos tres quatre cinc sis",
        "speaker": None,
        "is_user": False,
        "person_id": None,
        "translations": [],
    }

    result = voiceprint.diarize_segments(clip, [original])

    assert [item["speaker"] for item in result] == ["spk_0", "spk_1"]
    assert [(item["start"], item["end"]) for item in result] == [(0.0, 3.0), (3.0, 6.0)]
    assert " ".join(item["text"] for item in result) == original["text"]
    assert result[0]["id"] == "one"
    assert result[1]["id"] != "one"


def test_provider_diarization_is_not_replaced_by_local_service(monkeypatch, tmp_path):
    _configure(monkeypatch)
    from selfhost import voiceprint

    monkeypatch.setattr(
        voiceprint,
        "remote_diarization",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not be called")),
    )
    original = [{"id": "one", "start": 0.0, "end": 2.0, "text": "Bon dia", "speaker": "spk_7"}]
    assert voiceprint.diarize_segments(tmp_path / "does-not-exist.wav", original) == original


def test_worker_voice_enrichment_continues_when_optional_service_fails(monkeypatch, tmp_path):
    from selfhost import worker

    original = [{"id": "one", "start": 0.0, "end": 2.0, "text": "Bon dia", "speaker": None}]
    monkeypatch.setattr(worker, "diarize_segments", lambda *_args: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(worker, "classify_segments", lambda *_args: (_ for _ in ()).throw(RuntimeError("offline")))
    assert worker.enrich_speaker_labels("user", tmp_path / "clip.wav", original, "job") == original
