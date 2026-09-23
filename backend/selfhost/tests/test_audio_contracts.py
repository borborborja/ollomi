import wave
import struct
import ctypes
import ctypes.util
import math
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocketDisconnect

from selfhost.worker import merge_audio_part


def _receive_live_ready(socket):
    event = socket.receive_json()
    assert event["type"] == "service_status"
    assert event["status"] == "ready"
    return event


def _receive_processing_started(socket):
    while True:
        event = socket.receive_json()
        if event["type"] == "processing_started":
            return event
        assert event["type"] == "service_status"


def test_real_lc3_frame_roundtrip_when_library_available():
    from selfhost import lc3_audio

    # CI runs in the backend image, where liblc3-0 must be installed. Developers
    # without the system library can still run the other contract tests.
    library_path = ctypes.util.find_library("lc3")
    if not library_path:
        pytest.skip("liblc3 is not installed on this host")
    library = ctypes.CDLL(library_path)
    library.lc3_encoder_size.argtypes = (ctypes.c_int, ctypes.c_int)
    library.lc3_encoder_size.restype = ctypes.c_uint
    library.lc3_setup_encoder.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)
    library.lc3_setup_encoder.restype = ctypes.c_void_p
    library.lc3_encode.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
    )
    library.lc3_encode.restype = ctypes.c_int
    memory = ctypes.create_string_buffer(library.lc3_encoder_size(10000, 16000))
    encoder = library.lc3_setup_encoder(10000, 16000, 0, memory)
    samples = (ctypes.c_int16 * 160)(*[int(10000 * math.sin(i * 0.1)) for i in range(160)])
    frame = ctypes.create_string_buffer(30)
    assert library.lc3_encode(encoder, 0, samples, 1, 30, frame) == 0
    decoded = lc3_audio.Lc3Decoder().decode(frame.raw)
    assert len(decoded) == 320
    assert any(decoded)


def test_conversation_audio_parts_follow_transcript_offsets_after_retry():
    from selfhost.db import wire

    stamp = datetime.now(timezone.utc)
    row = SimpleNamespace(
        id="conversation",
        kind="conversation",
        created_at=stamp,
        updated_at=stamp,
        data={
            "file_ids": ["first", "second"],
            "audio_files": [
                {"id": "second", "duration": 4},
                {"id": "first", "duration": 5},
            ],
        },
    )
    result = wire(row)
    assert [part["id"] for part in result["audio_files"]] == ["first", "second"]
    assert [part["id"] for part in row.data["audio_files"]] == ["second", "first"]


def test_reconnected_recording_retains_parts_and_retry_is_idempotent():
    first = [{"id": "a", "start": 0.0, "end": 2.0, "text": "first"}]
    data = {
        "file_ids": ["one", "two"],
        "audio_files": [{"id": "one", "duration": 5.0}],
        "transcript_segments": merge_audio_part({"file_ids": ["one"]}, "one", first, 5),
    }
    second = [{"id": "b", "start": 0.0, "end": 3.0, "text": "second"}]
    combined = merge_audio_part(data, "two", second, 4)
    assert [s["text"] for s in combined] == ["first", "second"]
    assert combined[1]["start"] == 5
    data["transcript_segments"] = combined
    assert merge_audio_part(data, "two", second, 4) == combined


def test_live_capture_socket_requires_auth_and_preserves_conversation_owner(client, admin):
    conversation_id = "00000000-0000-0000-0000-000000000111"
    path = "/v4/listen?codec=pcm16&sample_rate=16000&source=omi&client_conversation_id=" + conversation_id

    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect(path):
            pass
    assert rejected.value.code == 4401

    with client.websocket_connect(path, headers=admin) as socket:
        assert socket.receive_json() == {
            "type": "last_memory",
            "memory_id": conversation_id,
        }
        assert _receive_live_ready(socket)["source"] == "omi"
        socket.send_json({"type": "stop"})

    from selfhost.db import Record, transaction

    with transaction() as db:
        conversation = db.get(Record, conversation_id)
        assert conversation is not None
        assert conversation.user_id == client.get("/v1/auth/me", headers=admin).json()["uid"]
        assert conversation.data["status"] == "in_progress"
        assert conversation.data["source"] == "omi"


def test_live_capture_socket_rejects_unsupported_codec(client, admin):
    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect("/v4/listen?codec=mp3", headers=admin):
            pass
    assert rejected.value.code == 4400


def test_friend_pendant_socket_decodes_frames_and_queues_transcription(client, admin, monkeypatch):
    from selfhost import lc3_audio

    class FakeDecoder:
        def decode(self, frame):
            assert frame == b"\x01" * 30
            return struct.pack("<160h", *([123] * 160))

    monkeypatch.setattr(lc3_audio, "Lc3Decoder", FakeDecoder)
    with client.websocket_connect(
        "/v4/listen?codec=lc3_fs1030&sample_rate=16000&source=friend_com", headers=admin
    ) as socket:
        conversation_id = socket.receive_json()["memory_id"]
        _receive_live_ready(socket)
        for _ in range(3):
            socket.send_bytes(b"\x01" * 30)
        socket.send_json({"type": "stop"})
        job = _receive_processing_started(socket)
    assert job["type"] == "processing_started"

    from selfhost.audio import storage_path
    from selfhost.db import Job, Record, transaction

    with transaction() as db:
        row = db.get(Record, conversation_id)
        assert row.data["status"] == "processing"
        assert row.data["source"] == "friend_com"
        queued = db.get(Job, job["job_id"])
        assert queued.status == "queued"
        path = storage_path(row.user_id, queued.payload["file_id"])
    with wave.open(str(path)) as recording:
        assert recording.getframerate() == 16000
        assert recording.getnframes() == 480
        assert recording.readframes(480) == struct.pack("<480h", *([123] * 480))

    from selfhost import worker

    monkeypatch.setattr(
        worker,
        "transcribe_file",
        lambda profile, clip, language="auto": [
            {"id": "friend-segment", "start": 0.0, "end": 0.03, "text": "Prova Friend", "speaker": None}
        ],
    )
    monkeypatch.setattr(worker, "enrich_speaker_labels", lambda uid, clip, batch, job_id: batch)
    monkeypatch.setattr(
        worker,
        "enrichment",
        lambda *args, **kwargs: {
            "title": "Prova Friend",
            "overview": "Prova",
            "emoji": "",
            "category": "other",
            "events": [],
            "action_items": [],
            "decisions": [],
            "memories": [],
            "goals": [],
            "people": [],
        },
    )
    worker.run_job(job["job_id"])
    with transaction() as db:
        conversation = db.get(Record, conversation_id)
        assert conversation.data["status"] == "completed"
        assert conversation.data["transcript_segments"][0]["text"] == "Prova Friend"


def test_friend_pendant_socket_requires_16khz(client, admin):
    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect("/v4/listen?codec=lc3_fs1030&sample_rate=48000", headers=admin):
            pass
    assert rejected.value.code == 4400


def test_omi_pcm8_capture_decodes_unsigned_samples(client, admin):
    with client.websocket_connect("/v4/listen?codec=pcm8&sample_rate=16000&source=omi", headers=admin) as socket:
        conversation_id = socket.receive_json()["memory_id"]
        _receive_live_ready(socket)
        socket.send_bytes(bytes([128]) * 160)
        received = socket.receive_json()
        assert received["status"] == "audio_received"
        assert received["source"] == "omi"
        assert 0 <= received["audio_level"] <= 1
        socket.send_json({"type": "stop"})
        job_id = socket.receive_json()["job_id"]

    from selfhost.audio import storage_path
    from selfhost.db import Job, Record, transaction

    with transaction() as db:
        row = db.get(Record, conversation_id)
        path = storage_path(row.user_id, db.get(Job, job_id).payload["file_id"])
    with wave.open(str(path)) as recording:
        assert recording.getnframes() == 160
        assert recording.readframes(160) == bytes(320)


def test_omi_opus_capture_decodes_real_packet_when_library_available(client, admin):
    try:
        import opuslib
    except Exception:
        pytest.skip("libopus is not installed on this host")

    encoder = opuslib.Encoder(16000, 1, opuslib.APPLICATION_AUDIO)
    packet = encoder.encode(struct.pack("<320h", *([100] * 320)), 320)
    with client.websocket_connect("/v4/listen?codec=opus_fs320&sample_rate=16000&source=omi", headers=admin) as socket:
        conversation_id = socket.receive_json()["memory_id"]
        _receive_live_ready(socket)
        socket.send_bytes(packet)
        assert socket.receive_json()["status"] == "audio_received"
        socket.send_json({"type": "stop"})
        job_id = socket.receive_json()["job_id"]

    from selfhost.audio import storage_path
    from selfhost.db import Job, Record, transaction

    with transaction() as db:
        row = db.get(Record, conversation_id)
        path = storage_path(row.user_id, db.get(Job, job_id).payload["file_id"])
    with wave.open(str(path)) as recording:
        assert recording.getnframes() == 320
        assert len(recording.readframes(320)) == 640


def test_omi_pcm_capture_reaches_completed_transcript(client, admin, monkeypatch):
    from selfhost import worker

    with client.websocket_connect("/v4/listen?codec=pcm16&sample_rate=16000&source=omi", headers=admin) as socket:
        conversation_id = socket.receive_json()["memory_id"]
        _receive_live_ready(socket)
        socket.send_bytes(struct.pack("<16000h", *([100] * 16000)))
        assert socket.receive_json()["status"] == "audio_received"
        socket.send_json({"type": "stop"})
        job_id = socket.receive_json()["job_id"]

    monkeypatch.setattr(
        worker,
        "transcribe_file",
        lambda profile, clip, language="auto": [
            {"id": "segment-1", "start": 0.0, "end": 1.0, "text": "Prova Omi", "speaker": None}
        ],
    )
    monkeypatch.setattr(worker, "enrich_speaker_labels", lambda uid, clip, batch, job_id: batch)
    monkeypatch.setattr(
        worker,
        "enrichment",
        lambda *args, **kwargs: {
            "title": "Prova Omi",
            "overview": "Prova",
            "emoji": "",
            "category": "other",
            "events": [],
            "action_items": [],
            "decisions": [],
            "memories": [],
            "goals": [],
            "people": [],
        },
    )
    worker.run_job(job_id)

    from selfhost.db import Job, Record, transaction

    with transaction() as db:
        conversation = db.get(Record, conversation_id)
        assert conversation.data["status"] == "completed"
        assert conversation.data["source"] == "omi"
        assert conversation.data["transcript_segments"][0]["text"] == "Prova Omi"
        assert db.get(Job, job_id).status == "completed"


def test_live_preview_failure_does_not_truncate_device_audio(client, admin, monkeypatch):
    from selfhost import audio

    def preview_fails(*args, **kwargs):
        raise RuntimeError("temporary STT outage")

    monkeypatch.setattr(audio, "transcribe_file", preview_fails)
    with client.websocket_connect("/v4/listen?codec=pcm16&sample_rate=16000&source=omi", headers=admin) as socket:
        conversation_id = socket.receive_json()["memory_id"]
        _receive_live_ready(socket)
        socket.send_bytes(bytes(8 * 16000 * 2))
        assert socket.receive_json()["status"] == "audio_received"
        assert socket.receive_json()["status"] == "transcribing"
        assert socket.receive_json()["status"] == "live_stt_unavailable"
        socket.send_bytes(bytes(16000 * 2))
        socket.send_json({"type": "stop"})
        job_id = socket.receive_json()["job_id"]

    from selfhost.audio import storage_path
    from selfhost.db import Job, Record, transaction

    with transaction() as db:
        row = db.get(Record, conversation_id)
        path = storage_path(row.user_id, db.get(Job, job_id).payload["file_id"])
    with wave.open(str(path)) as recording:
        assert recording.getnframes() == 9 * 16000


def test_empty_live_preview_reports_no_speech_and_keeps_final_audio(client, admin, monkeypatch):
    from selfhost import audio

    monkeypatch.setattr(audio, "transcribe_file", lambda *args, **kwargs: [])
    with client.websocket_connect("/v4/listen?codec=pcm16&sample_rate=16000&source=omi", headers=admin) as socket:
        conversation_id = socket.receive_json()["memory_id"]
        _receive_live_ready(socket)
        socket.send_bytes(bytes(8 * 16000 * 2))
        assert socket.receive_json()["status"] == "audio_received"
        assert socket.receive_json()["status"] == "transcribing"
        assert socket.receive_json()["status"] == "no_speech"
        socket.send_json({"type": "stop"})
        job_id = _receive_processing_started(socket)["job_id"]

    from selfhost.audio import storage_path
    from selfhost.db import Job, Record, transaction

    with transaction() as db:
        row = db.get(Record, conversation_id)
        path = storage_path(row.user_id, db.get(Job, job_id).payload["file_id"])
    with wave.open(str(path)) as recording:
        assert recording.getnframes() == 8 * 16000


def test_saturated_preview_queue_skips_preview_but_not_durable_audio(client, admin, monkeypatch):
    from selfhost import audio

    release_preview = threading.Event()

    def slow_preview(*args, **kwargs):
        release_preview.wait(timeout=5)
        return []

    monkeypatch.setattr(audio, "transcribe_file", slow_preview)
    try:
        with client.websocket_connect("/v4/listen?codec=pcm16&sample_rate=16000&source=omi", headers=admin) as socket:
            conversation_id = socket.receive_json()["memory_id"]
            _receive_live_ready(socket)
            socket.send_bytes(bytes(32 * 16000 * 2))
            statuses = []
            while not {"transcription_delayed", "transcribing"}.issubset(statuses):
                event = socket.receive_json()
                if event["type"] == "service_status":
                    statuses.append(event["status"])
            assert "audio_received" in statuses
            assert "transcribing" in statuses
            socket.send_json({"type": "stop"})
            job_id = _receive_processing_started(socket)["job_id"]
    finally:
        release_preview.set()

    from selfhost.audio import storage_path
    from selfhost.db import Job, Record, transaction

    with transaction() as db:
        row = db.get(Record, conversation_id)
        path = storage_path(row.user_id, db.get(Job, job_id).payload["file_id"])
    with wave.open(str(path)) as recording:
        assert recording.getnframes() == 32 * 16000


def test_audio_retention_is_snapshotted_per_job(client, admin, monkeypatch):
    from selfhost import worker
    from selfhost.audio import storage_path
    from selfhost.db import Job, Record, transaction

    extraction = {
        "title": "Retention",
        "overview": "",
        "emoji": "",
        "category": "other",
        "events": [],
        "action_items": [],
        "decisions": [],
        "memories": [],
        "goals": [],
        "people": [],
    }
    monkeypatch.setattr(worker, "enrichment", lambda *args, **kwargs: extraction)

    def admit(name):
        response = client.post(
            "/v1/import/audio",
            headers=admin,
            files={"file": (name, b"durable source", "audio/wav")},
        )
        assert response.status_code == 202
        return response.json()["job_id"]

    discarded_job_id = admit("discard.wav")
    assert client.post("/v1/users/private-cloud-sync?value=true", headers=admin).status_code == 200
    retained_job_id = admit("retain.wav")

    for job_id in (discarded_job_id, retained_job_id):
        claimed = worker.claim(job_id)
        worker.finish_conversation(claimed, [{"text": "done", "start": 0, "end": 1}])

    with transaction() as db:
        discarded_job = db.get(Job, discarded_job_id)
        retained_job = db.get(Job, retained_job_id)
        assert discarded_job.payload["retain_audio"] is False
        assert retained_job.payload["retain_audio"] is True
        discarded_file_id = discarded_job.payload["file_id"]
        retained_file_id = retained_job.payload["file_id"]
        assert db.get(Record, discarded_file_id) is None
        assert db.get(Record, retained_file_id) is not None
        purge_job = next(
            job
            for job in db.query(Job).filter(Job.kind == "purge_files")
            if discarded_file_id in job.payload["file_ids"]
        )
        retained_conversation = db.get(Record, retained_job.payload["conversation_id"])
        assert retained_conversation.data["file_ids"] == [retained_file_id]
        assert storage_path(retained_job.user_id, retained_file_id).is_file()
        discarded_path = storage_path(discarded_job.user_id, discarded_file_id)
        assert discarded_path.is_file()

    worker.run_job(purge_job.id)
    assert not discarded_path.exists()


def test_legacy_job_without_retention_snapshot_keeps_audio(client, admin, monkeypatch):
    from selfhost import worker
    from selfhost.db import Job, Record, transaction

    response = client.post(
        "/v1/import/audio",
        headers=admin,
        files={"file": ("legacy.wav", b"legacy source", "audio/wav")},
    )
    job_id = response.json()["job_id"]
    with transaction() as db:
        job = db.get(Job, job_id)
        job.payload = {key: value for key, value in job.payload.items() if key != "retain_audio"}
        file_id = job.payload["file_id"]
    monkeypatch.setattr(
        worker,
        "enrichment",
        lambda *args, **kwargs: {
            "title": "Legacy",
            "overview": "",
            "emoji": "",
            "category": "other",
            "events": [],
            "action_items": [],
            "decisions": [],
            "memories": [],
            "goals": [],
            "people": [],
        },
    )
    worker.finish_conversation(worker.claim(job_id), [{"text": "done", "start": 0, "end": 1}])
    with transaction() as db:
        assert db.get(Record, file_id) is not None


def test_playback_ticket_is_owner_bound_and_revoked_at_logout(client, admin, other):
    from selfhost.db import Record, transaction

    accepted = client.post(
        "/v1/import/audio",
        headers=admin,
        files={"file": ("speech.wav", b"audio", "audio/wav")},
    ).json()
    with transaction() as db:
        from selfhost.db import Job

        job = db.get(Job, accepted["job_id"])
        conversation = db.get(Record, job.payload["conversation_id"])
        conversation.data = {
            **conversation.data,
            "audio_files": [{"id": job.payload["file_id"], "duration": 1}],
        }
        cid = conversation.id
    assert client.get(f"/v1/sync/audio/{cid}/urls", headers=other).status_code == 404
    response = client.get(f"/v1/sync/audio/{cid}/urls", headers=admin)
    assert response.status_code == 200
    url = response.json()["audio_files"][0]["signed_url"]
    assert client.get(url).content == b"audio"
    assert client.get(url.replace("/v1/audio/", "/v1/audio/00000000-0000-0000-0000-000000000000")).status_code in {
        401,
        404,
        422,
    }
    from selfhost.db import Session
    from sqlalchemy import update

    with transaction() as db:
        db.execute(update(Session).values(revoked=True))
    assert client.get(url).status_code == 401


def test_truncated_wal_is_rejected_without_acceptance(client, admin, tmp_path):
    import struct
    import pytest
    from fastapi import HTTPException
    from selfhost.sync import decode_bin

    source = tmp_path / "audio.bin"
    source.write_bytes(struct.pack("<I", 320) + b"\x00" * 318)
    with pytest.raises(HTTPException) as error:
        decode_bin(source, tmp_path / "out.wav", "audio_phone_pcm16_16000_1_fs320_1.bin")
    assert error.value.status_code == 422
    assert source.exists()
    source.write_bytes(struct.pack("<I", 320) + b"\x00" * 320)
    decode_bin(source, tmp_path / "out.wav", "audio_phone_pcm16_16000_1_fs320_1.bin")
    with wave.open(str(tmp_path / "out.wav")) as audio:
        assert audio.getnframes() == 160


def test_friend_pendant_batch_wal_decodes_to_pcm16(tmp_path, monkeypatch):
    from selfhost import lc3_audio
    from selfhost.sync import decode_bin

    class FakeDecoder:
        def decode(self, frame):
            assert frame == b"\x02" * 30
            return struct.pack("<160h", *([456] * 160))

    monkeypatch.setattr(lc3_audio, "Lc3Decoder", FakeDecoder)
    source = tmp_path / "audio_omibatch_lc3_fs1030_16000_1_fs160_1.bin"
    source.write_bytes((struct.pack("<I", 30) + b"\x02" * 30) * 3)
    destination = tmp_path / "decoded.wav"
    decode_bin(source, destination, source.name)
    with wave.open(str(destination)) as recording:
        assert recording.getsampwidth() == 2
        assert recording.getnframes() == 480
        assert recording.readframes(480) == struct.pack("<480h", *([456] * 480))


def test_friend_pendant_batch_wal_rejects_bad_frame(tmp_path, monkeypatch):
    from fastapi import HTTPException
    from selfhost import lc3_audio
    from selfhost.sync import decode_bin

    class FakeDecoder:
        def decode(self, frame):
            if len(frame) != 30:
                raise ValueError("Friend Pendant LC3 frame must be 30 bytes")

    monkeypatch.setattr(lc3_audio, "Lc3Decoder", FakeDecoder)
    source = tmp_path / "audio_omibatch_lc3_fs1030_16000_1_fs160_1.bin"
    source.write_bytes(struct.pack("<I", 29) + b"\x02" * 29)
    with pytest.raises(HTTPException) as error:
        decode_bin(source, tmp_path / "bad.wav", source.name)
    assert error.value.status_code == 422


def test_manual_split_finishes_first_conversation_and_continues(client, admin, monkeypatch):
    from selfhost import audio

    monkeypatch.setattr(audio, "transcribe_file", lambda *args, **kwargs: [])
    with client.websocket_connect("/v4/listen?codec=pcm16&sample_rate=16000&source=omi", headers=admin) as socket:
        first_conversation = socket.receive_json()["memory_id"]
        _receive_live_ready(socket)
        socket.send_bytes(struct.pack("<16000h", *([100] * 16000)))
        assert socket.receive_json()["status"] == "audio_received"

        socket.send_json({"type": "split"})
        new_conversation = None
        first_job = None
        while new_conversation is None:
            event = socket.receive_json()
            if event["type"] == "processing_started":
                first_job = event
            elif event["type"] == "conversation_split":
                new_conversation = event["conversation_id"]
        assert new_conversation != first_conversation

        socket.send_bytes(struct.pack("<16000h", *([100] * 16000)))
        socket.send_json({"type": "stop"})
        second_job = _receive_processing_started(socket)

    from selfhost.db import Job, Record, transaction

    with transaction() as db:
        assert first_job is not None
        assert db.get(Job, first_job["job_id"]).payload["conversation_id"] == first_conversation
        assert db.get(Job, second_job["job_id"]).payload["conversation_id"] == new_conversation
        first = db.get(Record, first_conversation)
        second = db.get(Record, new_conversation)
        assert first is not None and second is not None
        assert first.data["status"] == "processing"

