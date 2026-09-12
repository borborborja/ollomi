import wave

from selfhost.worker import merge_audio_part


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
    assert client.get(
        url.replace("/v1/audio/", "/v1/audio/00000000-0000-0000-0000-000000000000")
    ).status_code in {401, 404, 422}
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
        decode_bin(
            source, tmp_path / "out.wav", "audio_phone_pcm16_16000_1_fs320_1.bin"
        )
    assert error.value.status_code == 422
    assert source.exists()
    source.write_bytes(struct.pack("<I", 320) + b"\x00" * 320)
    decode_bin(source, tmp_path / "out.wav", "audio_phone_pcm16_16000_1_fs320_1.bin")
    with wave.open(str(tmp_path / "out.wav")) as audio:
        assert audio.getnframes() == 160
