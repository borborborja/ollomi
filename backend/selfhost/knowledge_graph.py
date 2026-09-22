"""Owner-scoped, deterministic mind map derived from stored memories.

No external LLM call or separate graph database is required. The graph is
generated at read time so edits and deletions cannot leave stale nodes behind.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select

from selfhost.db import Record, transaction
from selfhost.security import current_user

router = APIRouter()

_MEMORY_LIMIT = 100
_CONVERSATION_LIMIT = 50
_TAG_LIMIT = 50


def _graph(db, user_id):
    rows = list(
        db.scalars(
            select(Record)
            .where(Record.user_id == user_id, Record.kind == "memory")
            .order_by(Record.created_at.desc(), Record.id)
            .limit(_MEMORY_LIMIT + 1)
        )
    )
    truncated = len(rows) > _MEMORY_LIMIT
    nodes = [{"id": "user-node", "label": "Me", "node_type": "user"}]
    edges = []
    categories = set()
    tags = set()
    conversations = set()

    conversation_rows = list(
        db.scalars(
            select(Record)
            .where(Record.user_id == user_id, Record.kind == "conversation")
            .order_by(Record.created_at.desc(), Record.id)
            .limit(_CONVERSATION_LIMIT + 1)
        )
    )
    truncated |= len(conversation_rows) > _CONVERSATION_LIMIT
    for row in conversation_rows[:_CONVERSATION_LIMIT]:
        if row.data.get("discarded"):
            continue
        if not conversations:
            nodes.append({"id": "category:conversations", "label": "Conversations", "node_type": "concept"})
            edges.append({"source_id": "user-node", "target_id": "category:conversations", "label": ""})
        conversation_id = "conversation:" + row.id
        title = str((row.data.get("structured") or {}).get("title") or "Conversation").strip()
        nodes.append({"id": conversation_id, "label": title[:120] or "Conversation", "node_type": "concept"})
        edges.append({"source_id": "category:conversations", "target_id": conversation_id, "label": ""})
        conversations.add(conversation_id)

    for row in rows[:_MEMORY_LIMIT]:
        content = str(row.data.get("content") or "").strip()
        if not content:
            continue
        memory_id = "memory:" + row.id
        nodes.append({"id": memory_id, "label": content[:120], "node_type": "concept"})

        category = str(row.data.get("category") or "Memories").strip()[:60] or "Memories"
        category_id = "memory-category:" + category.casefold()
        if category_id not in categories:
            categories.add(category_id)
            nodes.append({"id": category_id, "label": category, "node_type": "concept"})
            edges.append({"source_id": "user-node", "target_id": category_id, "label": ""})
        edges.append({"source_id": category_id, "target_id": memory_id, "label": ""})
        source_conversation = "conversation:" + str(row.data.get("conversation_id") or "")
        if source_conversation in conversations:
            edges.append({"source_id": source_conversation, "target_id": memory_id, "label": ""})

        raw_tags = row.data.get("tags")
        for raw_tag in raw_tags[:5] if isinstance(raw_tags, list) else []:
            tag = str(raw_tag).strip()[:60]
            if not tag:
                continue
            tag_id = "tag:" + tag.casefold()
            if tag_id not in tags:
                if len(tags) >= _TAG_LIMIT:
                    truncated = True
                    continue
                tags.add(tag_id)
                nodes.append({"id": tag_id, "label": tag, "node_type": "concept"})
            edges.append({"source_id": memory_id, "target_id": tag_id, "label": ""})

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_limit": _MEMORY_LIMIT + _CONVERSATION_LIMIT + _TAG_LIMIT + len(categories) + 2,
        "edge_limit": None,
        "truncated": truncated,
    }


@router.get("/v1/knowledge-graph")
def knowledge_graph(user=Depends(current_user)):
    with transaction() as db:
        return _graph(db, user.id)


@router.post("/v1/knowledge-graph/rebuild")
def rebuild_knowledge_graph(user=Depends(current_user)):
    # Compatibility with the app's rebuild contract: there is no asynchronous
    # materialization to wait for, because GET reads canonical records.
    with transaction() as db:
        graph = _graph(db, user.id)
    return {
        "status": "ready",
        "nodes_count": graph["node_count"],
        "edges_count": graph["edge_count"],
    }
