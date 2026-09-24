import struct
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from selfhost.db import Job, Record, User, now, transaction
from selfhost.records import conversation_data


def _live_ready(socket):
    event = socket.receive_json()
    assert event["type"] == "service_status"
    assert event["status"] == "ready"


def _processing_started(socket):
    while True:
        event = socket.receive_json()
        if event["type"] == "processing_started":
            return event
        assert event["type"] == "service_status"


def _owner(db):
    return db.scalar(select(User).where(User.email == "admin@test.local"))


def _conversation_jobs(db, conversation_id):
    return list(db.scalars(select(Job).where(Job.payload["conversation_id"].as_string() == conversation_id)))


def test_extract_json_payload_tolerates_fences_and_prose():
    from selfhost.worker import extract_json_payload

    assert extract_json_payload('```json\n{"title": "x"}\n```') == {"title": "x"}
    assert extract_json_payload('Aquí tens el resultat: {"title": "x"} gràcies') == {"title": "x"}
    with pytest.raises(ValueError):
        extract_json_payload("no json here")


def test_processing_started_frame_carries_the_memory(client, admin):
    conversation_id = "00000000-0000-0000-0000-0000000000aa"
    with client.websocket_connect(
        f"/v4/listen?codec=pcm16&sample_rate=16000&source=omi&client_conversation_id={conversation_id}",
        headers=admin,
    ) as socket:
        assert socket.receive_json() == {"type": "last_memory", "memory_id": conversation_id}
        _live_ready(socket)
        socket.send_bytes(struct.pack("<160h", *([100] * 160)))
        assert socket.receive_json()["status"] == "audio_received"
        socket.send_json({"type": "stop"})
        event = _processing_started(socket)

    assert event["memory"]["id"] == conversation_id
    assert event["memory"]["status"] == "processing"


def test_finalize_live_conversation_queues_audio_once(client, admin):
    conversation_id = "00000000-0000-0000-0000-0000000000bb"
    with transaction() as db:
        owner = _owner(db)
        db.add(
            Record(
                id=conversation_id,
                user_id=owner.id,
                kind="conversation",
                data=conversation_data({"status": "in_progress", "source": "phone", "file_ids": ["file-1"]}),
            )
        )
        db.add(Record(id="file-1", user_id=owner.id, kind="file", data={"name": "recording.wav"}))

    first = client.post("/v1/conversations", headers=admin, json={"conversation_id": conversation_id})
    assert first.status_code == 200
    assert first.json()["conversation"]["id"] == conversation_id
    second = client.post("/v1/conversations", headers=admin, json={"conversation_id": conversation_id})
    assert second.status_code == 200
    assert second.json()["conversation"]["id"] == conversation_id

    with transaction() as db:
        conversations = list(db.scalars(select(Record).where(Record.kind == "conversation")))
        assert len(conversations) == 1
        jobs = _conversation_jobs(db, conversation_id)
        assert len(jobs) == 1
        assert jobs[0].kind == "audio"
        assert conversations[0].data["status"] == "processing"


def test_completed_conversation_id_is_idempotent(client, admin):
    created = client.post(
        "/v1/conversations",
        headers=admin,
        json={"transcript_segments": [{"id": "s1", "text": "hola", "start": 0, "end": 1}]},
    ).json()
    conversation_id = created["conversation"]["id"]

    repeat = client.post("/v1/conversations", headers=admin, json={"conversation_id": conversation_id})
    assert repeat.status_code == 200
    assert repeat.json()["conversation"]["id"] == conversation_id
    with transaction() as db:
        assert len(list(db.scalars(select(Record).where(Record.kind == "conversation")))) == 1


def test_post_with_nothing_to_process_is_404(client, admin):
    assert client.post("/v1/conversations", headers=admin, json={}).status_code == 404


def test_enrichment_failure_publishes_transcript_with_fallback(client, admin, monkeypatch):
    from selfhost import worker

    created = client.post(
        "/v1/conversations",
        headers=admin,
        json={"transcript_segments": [{"id": "s1", "text": "Plan explícito", "start": 0, "end": 1}]},
    ).json()

    def boom(*args, **kwargs):
        raise ValueError("Invalid extraction JSON")

    monkeypatch.setattr(worker, "enrichment", boom)
    worker.run_job(created["job_id"])

    conversation = client.get("/v1/conversations/" + created["conversation"]["id"], headers=admin).json()
    assert conversation["status"] == "completed"
    assert conversation["enrichment_failed"] is True
    assert conversation["transcript_segments"][0]["text"] == "Plan explícito"
    assert conversation["structured"]["title"] == "Plan explícito"


def test_failed_media_job_marks_conversation_failed(client, admin, monkeypatch):
    from selfhost import worker

    conversation_id = "00000000-0000-0000-0000-0000000000cc"
    with transaction() as db:
        owner = _owner(db)
        db.add(
            Record(
                id=conversation_id,
                user_id=owner.id,
                kind="conversation",
                data=conversation_data({"status": "in_progress", "source": "phone", "file_ids": ["file-2"]}),
            )
        )
        db.add(Record(id="file-2", user_id=owner.id, kind="file", data={"name": "recording.wav"}))

    job_id = client.post("/v1/conversations", headers=admin, json={"conversation_id": conversation_id}).json()["job_id"]

    def provider_down(job):
        raise RuntimeError("provider down")

    monkeypatch.setattr(worker, "process_audio", provider_down)
    worker.run_job(job_id)

    with transaction() as db:
        conversation = db.get(Record, conversation_id)
        assert conversation.data["status"] == "failed"
        assert conversation.data["error"]
        failed = db.get(Job, job_id)
        assert failed.status == "failed"


def test_recover_requeues_failed_media_jobs_and_terminates_exhausted(client, admin, monkeypatch):
    from selfhost import worker

    retryable_id = "00000000-0000-0000-0000-0000000000dd"
    exhausted_id = "00000000-0000-0000-0000-0000000000ee"
    with transaction() as db:
        owner = _owner(db)
        db.add(
            Record(
                id=retryable_id,
                user_id=owner.id,
                kind="conversation",
                data=conversation_data({"status": "processing", "source": "phone", "file_ids": ["file-3"]}),
            )
        )
        db.add(
            Record(
                id=exhausted_id,
                user_id=owner.id,
                kind="conversation",
                data=conversation_data({"status": "processing", "source": "phone", "file_ids": ["file-4"]}),
            )
        )
        db.add(
            Job(
                id="job-retry",
                user_id=owner.id,
                kind="audio",
                status="failed",
                attempts=1,
                error="Processing failed: HTTPStatusError.",
                payload={"conversation_id": retryable_id, "file_id": "file-3"},
            )
        )
        db.add(
            Job(
                id="job-exhausted",
                user_id=owner.id,
                kind="enrich",
                status="failed",
                attempts=3,
                error="Processing failed: ValueError.",
                payload={"conversation_id": exhausted_id},
            )
        )
        stale = now() - timedelta(minutes=20)
        db.get(Record, retryable_id).updated_at = stale
        db.get(Record, exhausted_id).updated_at = stale
        db.get(Job, "job-retry").updated_at = stale
        db.get(Job, "job-exhausted").updated_at = stale

    monkeypatch.setattr(worker, "run_job", SimpleNamespace(delay=lambda job_id: None))
    worker.recover()

    with transaction() as db:
        assert db.get(Job, "job-retry").status == "queued"
        assert db.get(Job, "job-exhausted").status == "failed"
        assert db.get(Record, exhausted_id).data["status"] == "failed"
