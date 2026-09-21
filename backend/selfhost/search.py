import hashlib
import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text

from selfhost.config import settings
from selfhost.db import Record, transaction, wire
from selfhost.profiles import embed, selected_profile
from selfhost.security import current_user

router = APIRouter()


def generation(profile):
    return hashlib.sha256(
        (profile["id"] + ":" + profile["base_url"] + ":" + profile["model"] + ":" + str(profile["revision"])).encode()
    ).hexdigest()[:32]


def record_text(row):
    data = row.data
    if row.kind == "conversation":
        return (
            data.get("structured", {}).get("title", "")
            + "\n"
            + "\n".join(s.get("text", "") for s in data.get("transcript_segments", []))
        )
    if row.kind in {"goal", "calendar_event"}:
        return "\n".join(
            str(value)
            for value in (
                data.get("title"),
                data.get("description"),
                data.get("location"),
                " ".join(data.get("tags", [])),
            )
            if value
        )
    return "\n".join(
        str(value)
        for value in (data.get("content"), data.get("description"), data.get("owner"), " ".join(data.get("tags", [])))
        if value
    )


def index_record(uid, record_id, profile):
    with transaction() as db:
        row = db.get(Record, record_id)
        if row is None or row.user_id != uid:
            return
        content, kind = record_text(row), row.kind
        source_hash = hashlib.sha256(content.encode()).hexdigest()
    # Small chunks stay within the default embedding model's context window.
    chunks = [content[i : i + 2000] for i in range(0, len(content), 1800)] or [""]
    vectors = embed(profile, chunks, input_type="search_document")
    with transaction() as db:
        row = db.scalar(select(Record).where(Record.id == record_id).with_for_update())
        if row is None or row.user_id != uid:
            return
        if hashlib.sha256(record_text(row).encode()).hexdigest() != source_hash:
            raise RuntimeError("Record changed during indexing")
        db.execute(
            text("DELETE FROM embeddings WHERE record_id=:r AND generation=:g"),
            {"r": record_id, "g": generation(profile)},
        )
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            db.execute(
                text(
                    "INSERT INTO embeddings (record_id,user_id,generation,chunk_index,content,embedding) VALUES (:r,:u,:g,:i,:c,CAST(:v AS vector))"
                ),
                {
                    "r": record_id,
                    "u": uid,
                    "g": generation(profile),
                    "i": index,
                    "c": chunk,
                    "v": json.dumps(vector),
                },
            )
        index_text(uid, record_id, kind, content)


def typesense():
    return httpx.Client(
        base_url=settings().typesense_url.rstrip("/") + "/",
        headers={"X-TYPESENSE-API-KEY": settings().typesense_key.get_secret_value()},
        timeout=10,
        trust_env=False,
    )


def index_text(uid, record_id, kind, content):
    with typesense() as client:
        response = client.post(
            "collections/records/documents",
            params={"action": "upsert"},
            json={"id": record_id, "user_id": uid, "kind": kind, "content": content},
        )
        if response.status_code == 404:
            created = client.post(
                "collections",
                json={
                    "name": "records",
                    "fields": [
                        {"name": "user_id", "type": "string", "facet": True},
                        {"name": "kind", "type": "string", "facet": True},
                        {"name": "content", "type": "string"},
                    ],
                },
            )
            if created.status_code not in {201, 409}:
                created.raise_for_status()
            response = client.post(
                "collections/records/documents",
                params={"action": "upsert"},
                json={
                    "id": record_id,
                    "user_id": uid,
                    "kind": kind,
                    "content": content,
                },
            )
        response.raise_for_status()


def semantic_search(uid, query, limit=10):
    with transaction() as db:
        profile = selected_profile(db, uid, "embedding")
    vector = embed(profile, [query], input_type="search_query")[0]
    with transaction() as db:
        rows = db.execute(
            text(
                "SELECT record_id, content, embedding <=> CAST(:v AS vector) AS distance FROM embeddings WHERE user_id=:u AND generation=:g AND vector_dims(embedding)=:d ORDER BY distance LIMIT :n"
            ),
            {
                "v": json.dumps(vector),
                "u": uid,
                "g": generation(profile),
                "d": len(vector),
                "n": limit * 3,
            },
        )
        seen, results = set(), []
        for record_id, content, distance in rows:
            row = db.get(Record, record_id)
            if row and row.user_id == uid and record_id not in seen:
                results.append(
                    {
                        "record": wire(row),
                        "kind": row.kind,
                        "snippet": content,
                        "score": 1 - float(distance),
                    }
                )
                seen.add(record_id)
            if len(results) >= limit:
                break
        return results


@router.get("/v1/search")
def search(
    q: str = Query(min_length=1, max_length=2000),
    mode: str = "semantic",
    limit: int = Query(10, ge=1, le=50),
    user=Depends(current_user),
):
    try:
        if mode == "semantic":
            return {"results": semantic_search(user.id, q, limit)}
        if mode != "text":
            raise HTTPException(422, "Search mode must be text or semantic")
        with typesense() as client:
            response = client.get(
                "collections/records/documents/search",
                params={
                    "q": q,
                    "query_by": "content",
                    "filter_by": f"user_id:={user.id}",
                    "per_page": limit,
                },
            )
            if response.status_code == 404:
                return {"results": []}
            response.raise_for_status()
            ids = [hit["document"]["id"] for hit in response.json()["hits"]]
        with transaction() as db:
            return {
                "results": [
                    {"record": wire(row), "kind": row.kind}
                    for row in db.scalars(select(Record).where(Record.id.in_(ids), Record.user_id == user.id))
                ]
            }
    except httpx.HTTPError:
        raise HTTPException(503, "Search provider unavailable; indexing may still be pending") from None


def purge_index(ids):
    with typesense() as client:
        for record_id in ids:
            response = client.delete("collections/records/documents/" + record_id)
            if response.status_code != 404:
                response.raise_for_status()


def purge_owner_index(uid):
    with typesense() as client:
        response = client.delete("collections/records/documents", params={"filter_by": f"user_id:={uid}"})
        if response.status_code != 404:
            response.raise_for_status()


def purge_all_text_index():
    """Remove only the derived Typesense collection before a full rebuild.

    Records and vector embeddings remain in PostgreSQL.  This is deliberately
    separate from owner deletion: recovery needs to discard an index that may
    belong to a newer database snapshot without touching primary user data.
    """
    with typesense() as client:
        response = client.delete("collections/records")
        if response.status_code != 404:
            response.raise_for_status()
