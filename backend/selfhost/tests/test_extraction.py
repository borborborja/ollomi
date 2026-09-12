from selfhost.extraction import normalize_extraction


def test_extraction_preserves_explicit_data_without_promoting_ambiguous_dates():
    transcript = "Ana dijo: Envío el presupuesto el 2026-10-01 a las 10:00. La reunión será mañana."
    result = normalize_extraction(
        {
            "title": "Presupuesto",
            "category": "work",
            "action_items": [
                {
                    "description": "Enviar el presupuesto",
                    "assignee": "Ana",
                    "due_at": "2026-10-01T10:00:00+02:00",
                    "priority": "high",
                    "tags": ["ventas", "ventas"],
                    "source_quote": "Envío el presupuesto el 2026-10-01 a las 10:00.",
                }
            ],
            "events": [
                {
                    "title": "Reunión",
                    "start_at": "2026-10-02T09:00:00",  # No timezone: never schedule it.
                    "date_text": "mañana",
                    "attendees": ["Ana"],
                }
            ],
            "memories": [{"content": "Ana prepara presupuestos", "source_quote": "Ana dijo"}],
            "goals": [{"title": "Cerrar la venta", "target_at": "not-a-date"}],
            "people": [{"name": "Ana", "role": "ventas"}],
        },
        transcript,
    )

    task = result["action_items"][0]
    assert task["due_at"] == "2026-10-01T10:00:00+02:00"
    assert task["priority"] == "high"
    assert task["tags"] == ["ventas"]
    assert task["source_quote"].startswith("Envío")
    assert result["events"][0]["start_at"] is None
    assert result["events"][0]["date_text"] == "mañana"
    assert result["goals"][0]["target_at"] is None
    assert result["category"] == "work"


def test_extraction_drops_invalid_objects_and_keeps_legacy_string_results():
    result = normalize_extraction(
        {
            "action_items": ["Llamar a Marta", ""],
            "memories": ["Marta prefiere correo"],
            "events": [{"title": "Sin fecha"}],
            "decisions": [{"description": ""}],
        },
        "Llamar a Marta. Marta prefiere correo.",
    )

    assert [item["description"] for item in result["action_items"]] == ["Llamar a Marta"]
    assert [item["content"] for item in result["memories"]] == ["Marta prefiere correo"]
    assert result["events"] == []
    assert result["decisions"] == []


def test_finish_conversation_persists_export_ready_records(client, admin, monkeypatch):
    created = client.post(
        "/v1/conversations",
        headers=admin,
        json={"transcript_segments": [{"text": "Plan explícito", "start": 0, "end": 1}]},
    ).json()
    from selfhost import worker
    from selfhost.db import Record, transaction

    result = normalize_extraction(
        {
            "title": "Plan",
            "overview": "Resumen",
            "category": "work",
            "action_items": [{"description": "Enviar propuesta", "due_at": "2026-10-01T10:00:00+02:00"}],
            "events": [{"title": "Reunión", "start_at": "2026-10-02T10:00:00+02:00"}],
            "decisions": [{"description": "Usar CalDAV"}],
            "memories": [{"content": "El equipo usa CalDAV"}],
            "goals": [{"title": "Publicar integración"}],
        },
        "Plan explícito",
    )
    monkeypatch.setattr(worker, "enrichment", lambda *args, **kwargs: result)
    job = worker.claim(created["job_id"])
    worker.finish_conversation(job, [{"text": "Plan explícito"}])

    with transaction() as db:
        rows = list(db.query(Record).filter(Record.user_id == job.user_id))
        kinds = {row.kind for row in rows}
        task = next(row for row in rows if row.kind == "task")
        conversation = next(row for row in rows if row.kind == "conversation")
    assert {"task", "memory", "goal", "calendar_event", "decision"} <= kinds
    assert task.data["due_at"] == "2026-10-01T10:00:00+02:00"
    assert conversation.data["structured"]["events"][0]["title"] == "Reunión"
