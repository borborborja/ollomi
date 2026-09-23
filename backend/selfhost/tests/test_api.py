import io
import os
import wave

import pytest


def test_auth_rotation_revocation(client, admin):
    login = client.post(
        "/v1/auth/login",
        json={"email": "admin@test.local", "password": "admin-password-123"},
    ).json()
    rotated = client.post("/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert rotated.status_code == 200
    assert client.post("/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}).status_code == 401
    session = rotated.json()
    assert client.post("/v1/auth/logout", json={"refresh_token": session["refresh_token"]}).status_code == 200
    assert (
        client.get(
            "/v1/auth/me",
            headers={"Authorization": "Bearer " + session["access_token"]},
        ).status_code
        == 401
    )


def test_private_cloud_sync_is_persistent_and_user_scoped(client, admin, other):
    path = "/v1/users/private-cloud-sync"
    assert client.get(path, headers=admin).json() == {"private_cloud_sync_enabled": False}
    assert client.post(path + "?value=true", headers=admin).json() == {"status": "ok"}
    assert client.get(path, headers=admin).json() == {"private_cloud_sync_enabled": True}
    assert client.get(path, headers=other).json() == {"private_cloud_sync_enabled": False}


def test_readiness_requires_redis_and_typesense(client, monkeypatch):
    from selfhost import main

    class Redis:
        def ping(self):
            return True

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class Typesense:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, path):
            assert path == "health"
            return Response()

    monkeypatch.setattr(main.rate_limit, "redis", lambda: Redis())
    monkeypatch.setattr(main.search, "typesense", lambda: Typesense())
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ok"}

    class BrokenRedis:
        def ping(self):
            raise OSError("not reachable")

    monkeypatch.setattr(main.rate_limit, "redis", lambda: BrokenRedis())
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Ollomi dependencies unavailable"}


def test_role_and_secrets(client, admin, other):
    assert client.get("/v1/admin/users", headers=other).status_code == 403
    assert client.get("/v1/conversations").status_code == 401
    payload = {
        "name": "secret test",
        "purpose": "chat",
        "model": "test",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "never-return-this-key",
    }
    result = client.post("/v1/admin/ai-profiles", json=payload, headers=admin)
    assert result.status_code == 201
    assert "never-return-this-key" not in result.text
    assert "never-return-this-key" not in client.get("/v1/ai-profiles", headers=other).text
    assert "base_url" not in client.get("/v1/ai-profiles", headers=other).text


def test_environment_profiles_are_read_only_and_user_selectable(client, admin, monkeypatch):
    monkeypatch.setenv("OLLOMI_ALLOW_USER_MODEL_SELECTION", "true")
    monkeypatch.setenv("OLLOMI_CHAT1_PROVIDER", "custom")
    monkeypatch.setenv("OLLOMI_CHAT1_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("OLLOMI_CHAT1_MODEL", "qwen-test")
    monkeypatch.setenv("OLLOMI_CHAT2_PROVIDER", "custom")
    monkeypatch.setenv("OLLOMI_CHAT2_URL", "http://127.0.0.1:9999/v1")
    monkeypatch.setenv("OLLOMI_CHAT2_MODEL", "fallback-test")
    from selfhost.config import settings
    from selfhost.db import transaction
    from selfhost.profiles import selected_profile, sync_env_profiles

    settings.cache_clear()
    with transaction() as db:
        sync_env_profiles(db)

    status = client.get("/v1/ai-status", headers=admin).json()["chat"]
    assert status["managed_by_env"] is True
    assert status["selection_allowed"] is True
    assert [profile["model"] for profile in status["profiles"]] == [
        "qwen-test",
        "fallback-test",
    ]
    assert all(profile["status"] == "unknown" for profile in status["profiles"])
    assert status["active_profile_id"] == status["profiles"][0]["id"]
    selected = status["profiles"][1]["id"]
    assert client.put("/v1/users/me/ai-profiles", headers=admin, json={"chat": selected}).status_code == 200
    with transaction() as db:
        assert selected_profile(db, client.get("/v1/auth/me", headers=admin).json()["uid"], "chat")["id"] == selected
    assert (
        client.put(
            "/v1/admin/ai-profiles/" + status["profiles"][0]["id"],
            headers=admin,
            json={
                "name": "changed",
                "purpose": "chat",
                "base_url": "http://127.0.0.1:11434/v1",
                "model": "changed",
            },
        ).status_code
        == 409
    )


def test_environment_profiles_cannot_be_selected_when_the_server_disables_it(client, admin, monkeypatch):
    monkeypatch.setenv("OLLOMI_ALLOW_USER_MODEL_SELECTION", "false")
    monkeypatch.setenv("OLLOMI_CHAT1_PROVIDER", "custom")
    monkeypatch.setenv("OLLOMI_CHAT1_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("OLLOMI_CHAT1_MODEL", "qwen-test")
    from selfhost.config import settings
    from selfhost.db import transaction
    from selfhost.profiles import sync_env_profiles

    settings.cache_clear()
    with transaction() as db:
        sync_env_profiles(db)

    status = client.get("/v1/ai-status", headers=admin).json()["chat"]
    assert status["selection_allowed"] is False
    selected = status["profiles"][0]["id"]
    assert client.put("/v1/users/me/ai-profiles", headers=admin, json={"chat": selected}).status_code == 403


def test_ordered_provider_fallback_uses_second_profile(monkeypatch):
    from selfhost import profiles

    attempts = []
    events = []
    monkeypatch.setattr(profiles, "mark_profile_health", lambda *args, **kwargs: None)
    monkeypatch.setattr(profiles, "record_fallback", lambda **kwargs: events.append(kwargs))
    chain = {
        "id": "first",
        "purpose": "chat",
        "fallbacks": [{"id": "second", "purpose": "chat"}],
    }

    def operation(profile):
        attempts.append(profile["id"])
        if profile["id"] == "first":
            raise RuntimeError("provider unavailable")
        return "ok"

    assert profiles.call_with_fallback(chain, operation) == "ok"
    assert attempts == ["first", "second"]
    assert events == [
        {
            "purpose": "chat",
            "from_profile": "first",
            "to_profile": "second",
            "reason": "other",
            "outcome": "recovered",
        }
    ]


def test_environment_provider_presets_cover_supported_native_apis(monkeypatch):
    from selfhost import profiles

    for key in list(os.environ):
        if any(key.startswith(f"OLLOMI_{purpose}") for purpose in ("STT", "CHAT", "EMBEDDING")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OLLOMI_STT1_PROVIDER", "openai")
    monkeypatch.setenv("OLLOMI_STT1_MODEL", "whisper-1")
    monkeypatch.setenv("OLLOMI_STT2_PROVIDER", "gemini")
    monkeypatch.setenv("OLLOMI_STT2_MODEL", "gemini-3.5-transcribe")
    monkeypatch.setenv("OLLOMI_STT3_PROVIDER", "assemblyai")
    monkeypatch.setenv("OLLOMI_STT3_MODEL", "universal-3-5-pro")
    monkeypatch.setenv("OLLOMI_STT4_PROVIDER", "deepgram")
    monkeypatch.setenv("OLLOMI_STT4_MODEL", "nova-3")
    monkeypatch.setenv("OLLOMI_CHAT1_PROVIDER", "openrouter")
    monkeypatch.setenv("OLLOMI_CHAT1_MODEL", "openai/gpt-test")
    monkeypatch.setenv("OLLOMI_CHAT2_PROVIDER", "ollama-cloud")
    monkeypatch.setenv("OLLOMI_CHAT2_MODEL", "gemma-test")
    monkeypatch.setenv("OLLOMI_EMBEDDING1_PROVIDER", "ollama")
    monkeypatch.setenv("OLLOMI_EMBEDDING1_MODEL", "embedding-test")
    monkeypatch.setenv("OLLOMI_EMBEDDING1_DIMENSIONS", "1024")
    monkeypatch.setenv("OLLOMI_EMBEDDING2_PROVIDER", "voyage")
    monkeypatch.setenv("OLLOMI_EMBEDDING2_MODEL", "voyage-4-lite")
    monkeypatch.setenv("OLLOMI_EMBEDDING2_DIMENSIONS", "1024")
    monkeypatch.setenv("OLLOMI_EMBEDDING3_PROVIDER", "cohere")
    monkeypatch.setenv("OLLOMI_EMBEDDING3_MODEL", "embed-v4.0")
    monkeypatch.setenv("OLLOMI_EMBEDDING3_DIMENSIONS", "1024")
    monkeypatch.setattr(
        profiles,
        "validate_url",
        lambda value, external=False, allow_unresolved=False: value,
    )

    configured = profiles.env_profiles()
    assert configured["stt"][0]["base_url"] == "https://api.openai.com/v1"
    assert configured["stt"][1]["base_url"] == "https://generativelanguage.googleapis.com"
    assert configured["stt"][2]["base_url"] == "https://api.assemblyai.com/v2"
    assert configured["stt"][3]["base_url"] == "https://api.deepgram.com/v1"
    assert configured["chat"][0]["base_url"] == "https://openrouter.ai/api/v1"
    assert configured["chat"][1]["base_url"] == "https://ollama.com/v1"
    assert configured["embedding"][0]["base_url"] == "http://ollama:11434/v1"
    assert configured["embedding"][1]["base_url"] == "https://api.voyageai.com/v1"
    assert configured["embedding"][2]["base_url"] == "https://api.cohere.com/v2"


@pytest.mark.parametrize(
    "path,body",
    [
        ("/v3/memories", {"content": "Private fact"}),
        ("/v1/action-items", {"description": "Private task"}),
        ("/v1/folders", {"name": "Private folder"}),
    ],
)
def test_owner_isolation(client, admin, other, path, body):
    created = client.post(path, headers=admin, json=body).json()
    assert client.patch(path + "/" + created["id"], headers=other, json=body).status_code == 404
    assert client.delete(path + "/" + created["id"], headers=other).status_code == 404
    assert created["id"] not in client.get(path, headers=other).text
    assert created["id"] not in client.get("/v1/export", headers=other).text


def test_segment_edit_is_exact_and_references_are_owned(client, admin, other):
    body = {
        "transcript_segments": [
            {"id": "one", "text": "first", "start": 0, "end": 1},
            {"id": "two", "text": "second", "start": 1, "end": 2},
        ],
        "file_ids": ["outside-owner"],
        "visibility": "public",
    }
    created = client.post("/v1/conversations", headers=admin, json=body).json()["conversation"]
    assert created["visibility"] == "private"
    assert not created.get("file_ids")
    path = "/v1/conversations/" + created["id"]
    assert client.patch(path + "/segments/text", headers=admin, json={"index": 1, "text": "edited"}).status_code == 200
    result = client.get(path, headers=admin).json()
    assert [s["text"] for s in result["transcript_segments"]] == ["first", "edited"]
    assert client.get(path, headers=other).status_code == 404
    folder = client.post("/v1/folders", headers=other, json={"name": "other"}).json()
    assert client.patch(path, headers=admin, json={"folder_id": folder["id"]}).status_code == 404


def test_import_durable_owner_cancel_and_retry(client, admin, other):
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000)
    response = client.post(
        "/v1/import/audio",
        headers=admin,
        files={"file": ("voice.wav", audio.getvalue(), "audio/wav")},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert client.get("/v1/import/jobs/" + job_id, headers=other).status_code == 404
    from selfhost.db import Job, transaction
    from selfhost.audio import storage_path
    from selfhost.worker import claim, checkpoint, Cancelled

    with transaction() as db:
        job = db.get(Job, job_id)
        assert storage_path(job.user_id, job.payload["file_id"]).read_bytes() == audio.getvalue()
    claimed = claim(job_id)
    assert claim(job_id) is None
    assert client.post(f"/v1/import/jobs/{job_id}/cancel", headers=admin).status_code == 200
    with pytest.raises(Cancelled):
        checkpoint(claimed, 90)
    assert client.post(f"/v1/import/jobs/{job_id}/retry", headers=admin).json()["status"] == "queued"


def test_delete_cancels_pending_derivations(client, admin):
    created = client.post("/v1/conversations", headers=admin, json={}).json()
    assert client.delete("/v1/conversations/" + created["conversation"]["id"], headers=admin).status_code == 200
    from selfhost.worker import claim

    assert claim(created["job_id"]) is None


def test_invalid_deadline_is_not_a_server_error(client, admin):
    response = client.post(
        "/v1/action-items",
        headers=admin,
        json={"description": "x", "due_at": "yesterday-ish"},
    )
    assert response.status_code == 422


def test_provider_public_endpoint_requires_explicit_opt_in(client, admin):
    body = {
        "name": "external",
        "purpose": "chat",
        "model": "x",
        "base_url": "https://1.1.1.1/v1",
    }
    assert client.post("/v1/admin/ai-profiles", headers=admin, json=body).status_code == 422
    body["external"] = True
    assert client.post("/v1/admin/ai-profiles", headers=admin, json=body).status_code == 422


def test_password_reset_revokes_sessions(client, admin, other):
    user = client.get("/v1/auth/me", headers=other).json()
    assert (
        client.patch(
            "/v1/admin/users/" + user["id"],
            headers=admin,
            json={"password": "reset-password-123"},
        ).status_code
        == 200
    )
    assert client.get("/v1/auth/me", headers=other).status_code == 401


def test_mobile_onboarding_persists_language_without_cloud(client, admin, other):
    assert client.get("/v1/users/profile", headers=other).json()["email"] == "user@test.local"
    assert client.get("/v1/users/onboarding", headers=other).json()["completed"] is False
    languages = client.get("/v1/users/available-languages", headers=other).json()["languages"]
    assert {"name": "Español", "code": "es"} in languages
    saved = client.patch("/v1/users/language", headers=other, json={"language": "es"})
    assert saved.json() == {"status": "ok", "single_language_mode": False}
    assert client.get("/v1/users/language", headers=other).json()["language"] == "es"
    assert client.get("/v1/users/language", headers=admin).json()["language"] is None
    assert client.patch("/v1/users/language", headers=other, json={"language": 3}).status_code == 422
    assert client.patch("/v1/users/onboarding", headers=other, json={"completed": True}).status_code == 200
    assert client.get("/v1/users/onboarding", headers=other).json()["completed"] is True
    assert client.get("/v1/users/onboarding", headers=admin).json()["completed"] is False


def test_transcription_vocabulary_round_trip(client, admin, other):
    assert client.get("/v1/users/transcription-preferences", headers=other).json() == {
        "single_language_mode": False,
        "vocabulary": [],
    }
    saved = client.patch(
        "/v1/users/transcription-preferences",
        headers=other,
        json={"single_language_mode": True, "vocabulary": ["Ollomi", "Ollomi", "  Micapum  ", ""]},
    )
    assert saved.status_code == 200
    stored = client.get("/v1/users/transcription-preferences", headers=other).json()
    assert stored["single_language_mode"] is True
    assert stored["vocabulary"] == ["Ollomi", "Micapum"]
    # Preferences are per account.
    assert client.get("/v1/users/transcription-preferences", headers=admin).json()["vocabulary"] == []
    assert (
        client.patch("/v1/users/transcription-preferences", headers=other, json={"vocabulary": "Ollomi"}).status_code
        == 422
    )
