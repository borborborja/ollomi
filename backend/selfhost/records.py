"""Owner-scoped Omi mobile data contracts backed by PostgreSQL."""

import json
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select

from selfhost.db import (
    Event,
    Job,
    Record,
    User,
    emit,
    ident,
    now,
    owned,
    transaction,
    wire,
)
from selfhost.profiles import selected_profile
from selfhost.security import current_user, user_wire

router = APIRouter()


def conversation_data(data=None):
    return {
        "started_at": now().isoformat(),
        "finished_at": now().isoformat(),
        "source": "phone",
        "language": "auto",
        "status": "processing",
        "discarded": False,
        "imported": False,
        "visibility": "private",
        "starred": False,
        "transcript_segments": [],
        "photos": [],
        "apps_results": [],
        "plugins_results": [],
        "structured": {
            "title": "Nueva conversación",
            "overview": "",
            "emoji": "",
            "category": "other",
            "action_items": [],
            "events": [],
        },
        **(data or {}),
    }


def insert(db, uid, kind, data):
    row = Record(id=ident(), user_id=uid, kind=kind, data=data)
    db.add(row)
    db.flush()
    emit(db, uid, kind + "_created", {"id": row.id})
    if kind in {"conversation", "memory", "task"}:
        db.add(
            Job(
                user_id=uid,
                kind="index",
                payload={
                    "record_id": row.id,
                    "embedding": selected_profile(db, uid, "embedding"),
                },
            )
        )
    return row


def reindex_record(db, uid, record):
    if record.kind in {"conversation", "memory", "task"}:
        db.add(
            Job(
                user_id=uid,
                kind="index",
                payload={
                    "record_id": record.id,
                    "embedding": selected_profile(db, uid, "embedding"),
                },
            )
        )
    emit(db, uid, record.kind + "_updated", {"id": record.id})


def list_rows(db, uid, kind, limit=100, offset=0):
    return list(
        db.scalars(
            select(Record)
            .where(Record.user_id == uid, Record.kind == kind)
            .order_by(Record.created_at.desc(), Record.id)
            .offset(offset)
            .limit(limit)
        )
    )


@router.get("/v1/conversations")
def conversations(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    statuses: str = "",
    folder_id: str | None = None,
    starred: bool | None = None,
    user=Depends(current_user),
):
    with transaction() as db:
        query = select(Record).where(
            Record.user_id == user.id, Record.kind == "conversation"
        )
        if folder_id:
            query = query.where(Record.data["folder_id"].as_string() == folder_id)
        if starred is not None:
            query = query.where(Record.data["starred"].as_boolean() == starred)
        if statuses:
            query = query.where(
                Record.data["status"].as_string().in_(statuses.split(","))
            )
        return [
            wire(r)
            for r in db.scalars(
                query.order_by(Record.created_at.desc(), Record.id)
                .offset(offset)
                .limit(limit)
            )
        ]


@router.get("/v1/conversations/{record_id}")
def conversation(record_id: str, user=Depends(current_user)):
    with transaction() as db:
        return wire(owned(db, user.id, record_id, "conversation"))


@router.post("/v1/conversations")
def create_conversation(body: dict = Body(default={}), user=Depends(current_user)):
    with transaction() as db:
        row = insert(
            db,
            user.id,
            "conversation",
            conversation_data(
                {
                    k: v
                    for k, v in body.items()
                    if k
                    in {
                        "transcript_segments",
                        "language",
                        "source",
                        "started_at",
                        "finished_at",
                    }
                }
            ),
        )
        job = Job(
            user_id=user.id,
            kind="enrich",
            payload={
                "conversation_id": row.id,
                "chat": selected_profile(db, user.id, "chat"),
                "embedding": selected_profile(db, user.id, "embedding"),
            },
        )
        db.add(job)
        db.flush()
        return {"conversation": wire(row), "messages": [], "job_id": job.id}


@router.post("/v1/conversations/{record_id}/reprocess")
def reprocess(record_id: str, user=Depends(current_user)):
    with transaction() as db:
        row = owned(db, user.id, record_id, "conversation")
        row.data = {**row.data, "status": "processing"}
        job = Job(
            user_id=user.id,
            kind="enrich",
            payload={
                "conversation_id": row.id,
                "chat": selected_profile(db, user.id, "chat"),
                "embedding": selected_profile(db, user.id, "embedding"),
            },
        )
        db.add(job)
        db.flush()
        return {"conversation": wire(row), "messages": [], "job_id": job.id}


@router.patch("/v1/conversations/{record_id}")
def update_conversation(record_id: str, body: dict, user=Depends(current_user)):
    allowed = {"title", "overview", "folder_id"}
    if set(body) - allowed:
        raise HTTPException(422, "Unsupported conversation fields")
    with transaction() as db:
        row = owned(db, user.id, record_id, "conversation")
        data = dict(row.data)
        if "folder_id" in body:
            if body["folder_id"]:
                owned(db, user.id, body["folder_id"], "folder")
            data["folder_id"] = body["folder_id"]
        data["structured"] = {
            **data["structured"],
            **{k: v for k, v in body.items() if k in {"title", "overview"}},
        }
        row.data = data
        reindex_record(db, user.id, row)
        return wire(row)


@router.patch("/v1/conversations/{record_id}/{field}")
def conversation_field(
    record_id: str,
    field: str,
    value: str | None = None,
    title: str | None = None,
    starred: bool | None = None,
    body: dict = Body(default={}),
    user=Depends(current_user),
):
    with transaction() as db:
        row = owned(db, user.id, record_id, "conversation")
        data = dict(row.data)
        if field == "title":
            data["structured"] = {
                **data["structured"],
                "title": title or body.get("title", ""),
            }
        elif field == "summary":
            data["structured"] = {
                **data["structured"],
                "overview": body.get("overview", body.get("summary", "")),
            }
        elif field == "starred":
            data["starred"] = (
                starred if starred is not None else body.get("starred", False)
            )
        elif field == "visibility":
            if value != "private":
                raise HTTPException(
                    422, "Public sharing is not enabled; use an authenticated export"
                )
            data["visibility"] = "private"
        else:
            raise HTTPException(404, "Unknown conversation operation")
        row.data = data
        reindex_record(db, user.id, row)
        emit(db, user.id, "conversation_updated", {"id": row.id})
        return {"status": "ok", "conversation": wire(row)}


@router.patch("/v1/conversations/{record_id}/segments/text")
def edit_segment(record_id: str, body: dict, user=Depends(current_user)):
    with transaction() as db:
        row = owned(db, user.id, record_id, "conversation")
        segments = [dict(s) for s in row.data["transcript_segments"]]
        index = body.get("segment_idx", body.get("index"))
        matches = [
            s
            for i, s in enumerate(segments)
            if (
                body.get("segment_id") is not None and s.get("id") == body["segment_id"]
            )
            or i == index
        ]
        if not matches or not isinstance(body.get("text"), str):
            raise HTTPException(422, "Invalid segment or text")
        matches[0]["text"] = body["text"]
        row.data = {**row.data, "transcript_segments": segments}
        reindex_record(db, user.id, row)
        return {"status": "ok"}


@router.patch("/v1/conversations/{record_id}/segments/assign-bulk")
def assign_segments(record_id: str, body: dict, user=Depends(current_user)):
    with transaction() as db:
        row = owned(db, user.id, record_id, "conversation")
        if body.get("person_id"):
            owned(db, user.id, body["person_id"], "person")
        indices = set(body.get("segment_indices", []))
        segments = [dict(s) for s in row.data["transcript_segments"]]
        for i, segment in enumerate(segments):
            if i in indices or segment.get("id") in body.get("segment_ids", []):
                segment.update(
                    person_id=body.get("person_id"), is_user=body.get("is_user", False)
                )
        row.data = {**row.data, "transcript_segments": segments}
        reindex_record(db, user.id, row)
        return {"status": "ok"}


def delete_record(uid, record_id, kind):
    with transaction() as db:
        row = owned(db, uid, record_id, kind)
        deleted_ids = [record_id]
        if kind == "conversation":
            for job in db.scalars(
                select(Job)
                .where(
                    Job.user_id == uid,
                    Job.payload["conversation_id"].as_string() == record_id,
                )
                .with_for_update()
            ):
                job.status, job.lease_token = "cancelled", None
            for child in db.scalars(
                select(Record).where(
                    Record.user_id == uid,
                    Record.data["conversation_id"].as_string() == record_id,
                )
            ):
                deleted_ids.append(child.id)
                db.delete(child)
            db.add(
                Job(
                    user_id=uid,
                    kind="purge_files",
                    payload={
                        "conversation_id": record_id,
                        "file_ids": row.data.get("file_ids", []),
                    },
                )
            )
        db.add(
            Job(user_id=uid, kind="purge_index", payload={"record_ids": deleted_ids})
        )
        db.delete(row)
        emit(db, uid, kind + "_deleted", {"id": record_id})
    return {"status": "ok"}


@router.delete("/v1/conversations/{record_id}")
def remove_conversation(record_id: str, user=Depends(current_user)):
    return delete_record(user.id, record_id, "conversation")


@router.get("/v3/memories")
def memories(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user=Depends(current_user),
):
    with transaction() as db:
        return [wire(r) for r in list_rows(db, user.id, "memory", limit, offset)]


@router.post("/v3/memories")
def create_memory(body: dict, user=Depends(current_user)):
    content = str(body.get("content", "")).strip()
    if not content or len(content) > 20000:
        raise HTTPException(422, "Memory content must contain 1–20000 characters")
    with transaction() as db:
        row = insert(
            db,
            user.id,
            "memory",
            {
                "content": content,
                "category": body.get("category", "manual"),
                "visibility": "private",
                "manually_added": True,
                "reviewed": False,
                "tags": [],
            },
        )
        return wire(row)


@router.patch("/v3/memories/{record_id}")
def edit_memory(record_id: str, body: dict, user=Depends(current_user)):
    with transaction() as db:
        row = owned(db, user.id, record_id, "memory")
        row.data = {
            **row.data,
            **{
                k: v
                for k, v in body.items()
                if k in {"content", "category", "tags", "reviewed"}
            },
        }
        db.add(
            Job(
                user_id=user.id,
                kind="index",
                payload={
                    "record_id": row.id,
                    "embedding": selected_profile(db, user.id, "embedding"),
                },
            )
        )
        return wire(row)


@router.delete("/v3/memories/{record_id}")
def remove_memory(record_id: str, user=Depends(current_user)):
    return delete_record(user.id, record_id, "memory")


@router.get("/v1/action-items")
def tasks(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    completed: bool | None = None,
    conversation_id: str | None = None,
    user=Depends(current_user),
):
    with transaction() as db:
        query = select(Record).where(Record.user_id == user.id, Record.kind == "task")
        if completed is not None:
            query = query.where(Record.data["completed"].as_boolean() == completed)
        if conversation_id:
            query = query.where(
                Record.data["conversation_id"].as_string() == conversation_id
            )
        rows = list(
            db.scalars(
                query.order_by(Record.created_at.desc(), Record.id)
                .offset(offset)
                .limit(limit + 1)
            )
        )
        return {
            "action_items": [wire(r) for r in rows[:limit]],
            "has_more": len(rows) > limit,
        }


@router.post("/v1/action-items")
def create_task(body: dict, user=Depends(current_user)):
    if not str(body.get("description", "")).strip():
        raise HTTPException(422, "Task description required")
    with transaction() as db:
        if body.get("conversation_id"):
            owned(db, user.id, body["conversation_id"], "conversation")
        data = {
            "description": body["description"],
            "completed": bool(body.get("completed", False)),
            "due_at": body.get("due_at"),
            "conversation_id": body.get("conversation_id"),
        }
        if data["due_at"]:
            try:
                datetime.fromisoformat(data["due_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                raise HTTPException(422, "Invalid due_at") from None
        return wire(insert(db, user.id, "task", data))


@router.patch("/v1/action-items/{record_id}")
def update_task(record_id: str, body: dict, user=Depends(current_user)):
    with transaction() as db:
        row = owned(db, user.id, record_id, "task")
        if body.get("due_at"):
            try:
                datetime.fromisoformat(body["due_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                raise HTTPException(422, "Invalid due_at") from None
        row.data = {
            **row.data,
            **{
                k: v
                for k, v in body.items()
                if k in {"description", "completed", "due_at"}
            },
            **({"reminded": False} if "due_at" in body else {}),
        }
        reindex_record(db, user.id, row)
        return wire(row)


@router.delete("/v1/action-items/{record_id}")
def remove_task(record_id: str, user=Depends(current_user)):
    return delete_record(user.id, record_id, "task")


def collection_routes(prefix, kind, defaults):
    def read(
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
        user=Depends(current_user),
    ):
        with transaction() as db:
            return [wire(r) for r in list_rows(db, user.id, kind, limit, offset)]

    def create(body: dict, user=Depends(current_user)):
        with transaction() as db:
            return wire(
                insert(
                    db,
                    user.id,
                    kind,
                    {
                        **defaults,
                        **{k: v for k, v in body.items() if k not in {"id", "user_id"}},
                    },
                )
            )

    def patch(record_id: str, body: dict, user=Depends(current_user)):
        with transaction() as db:
            row = owned(db, user.id, record_id, kind)
            row.data = {
                **row.data,
                **{k: v for k, v in body.items() if k not in {"id", "user_id"}},
            }
            return wire(row)

    def remove(record_id: str, user=Depends(current_user)):
        return delete_record(user.id, record_id, kind)

    for path, endpoint, methods, name in [
        (prefix, read, ["GET"], "list"),
        (prefix, create, ["POST"], "create"),
        (prefix + "/{record_id}", patch, ["PATCH"], "update"),
        (prefix + "/{record_id}", remove, ["DELETE"], "delete"),
    ]:
        router.add_api_route(path, endpoint, methods=methods, name=kind + "_" + name)


collection_routes(
    "/v1/folders",
    "folder",
    {
        "name": "",
        "color": "#808080",
        "order": 0,
        "description": "",
        "conversation_count": 0,
    },
)
collection_routes("/v1/users/people", "person", {"name": "", "speech_samples": []})
collection_routes(
    "/v1/goals",
    "goal",
    {"title": "", "description": "", "progress": 0, "completed": False},
)


@router.get("/v1/events")
def events(
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(current_user),
):
    with transaction() as db:
        rows = list(
            db.scalars(
                select(Event)
                .where(Event.user_id == user.id, Event.id > after)
                .order_by(Event.id)
                .limit(limit)
            )
        )
        return {
            "events": [
                {
                    "id": r.id,
                    "type": r.type,
                    "data": r.data,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
            "cursor": rows[-1].id if rows else after,
        }


@router.get("/v1/users/me")
def profile(user=Depends(current_user)):
    return {
        **user.preferences,
        **user_wire(user),
        "name": user.name,
        "onboarding_completed": True,
    }


@router.patch("/v1/users/me")
def update_me(body: dict, user=Depends(current_user)):
    with transaction() as db:
        row = db.get(User, user.id)
        if "name" in body:
            row.name = str(body["name"])[:200]
        safe = {
            k: v
            for k, v in body.items()
            if k
            in {
                "language",
                "time_zone",
                "onboarding_completed",
                "notifications_enabled",
                "retention_days",
                "voice",
            }
        }
        row.preferences = {**row.preferences, **safe}
        return {**row.preferences, **user_wire(row)}


@router.get("/v1/export")
def export(user=Depends(current_user)):
    with transaction() as db:
        rows = db.scalars(
            select(Record).where(
                Record.user_id == user.id,
                Record.kind.not_in(["file", "connector", "plugin"]),
            )
        )
        result = {
            "format": "ollomi",
            "version": 1,
            "records": [{"kind": r.kind, **wire(r)} for r in rows],
        }
        return Response(
            json.dumps(result, ensure_ascii=False),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="ollomi-export.json"'
            },
        )
