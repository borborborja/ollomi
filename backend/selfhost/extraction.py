"""Validation for structured facts extracted from a conversation.

The chat model is useful for finding candidates, but it is not authoritative.
This module keeps the model output bounded, typed and safe to persist.  In
particular, dates without an offset are retained as prose instead of becoming
silent reminders in the wrong timezone.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


_CATEGORIES = {"work", "personal", "meeting", "learning", "health", "finance", "travel", "other"}
_PRIORITIES = {"low", "normal", "high", "urgent"}


def _text(value: Any, limit: int = 2000) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _list(value: Any, limit: int = 12, item_limit: int = 120) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _text(item, item_limit)
        if text and text not in result:
            result.append(text)
        if len(result) == limit:
            break
    return result


def _instant(value: Any) -> str | None:
    value = _text(value, 80)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.isoformat()


def _quote(value: Any, transcript: str) -> str:
    quote = _text(value, 500)
    return quote if quote and quote.casefold() in transcript.casefold() else ""


def _objects(value: Any, limit: int = 40) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value[:limit] if isinstance(item, dict)]


def normalize_extraction(raw: Any, transcript: str) -> dict[str, Any]:
    """Return the durable extraction schema, discarding malformed candidates."""
    raw = raw if isinstance(raw, dict) else {}
    tasks = []
    for item in _objects(raw.get("action_items")):
        description = _text(item.get("description"))
        if not description:
            continue
        tasks.append(
            {
                "description": description,
                "assignee": _text(item.get("assignee"), 200),
                "due_at": _instant(item.get("due_at")),
                "due_text": _text(item.get("due_text"), 200),
                "priority": item.get("priority") if item.get("priority") in _PRIORITIES else "normal",
                "tags": _list(item.get("tags"), 8, 60),
                "source_quote": _quote(item.get("source_quote"), transcript),
            }
        )
    # Older/smaller chat models sometimes return lists of strings.
    if not tasks:
        tasks = [{"description": value, "assignee": "", "due_at": None, "due_text": "", "priority": "normal", "tags": [], "source_quote": ""} for value in _list(raw.get("action_items"), 40, 2000)]

    memories = []
    for item in _objects(raw.get("memories")):
        content = _text(item.get("content"))
        if content:
            memories.append(
                {
                    "content": content,
                    "category": _text(item.get("category"), 80) or "interesting",
                    "tags": _list(item.get("tags"), 8, 60),
                    "source_quote": _quote(item.get("source_quote"), transcript),
                }
            )
    if not memories:
        memories = [{"content": value, "category": "interesting", "tags": [], "source_quote": ""} for value in _list(raw.get("memories"), 40, 2000)]

    events = []
    for item in _objects(raw.get("events")):
        title = _text(item.get("title"), 300)
        start_at = _instant(item.get("start_at"))
        date_text = _text(item.get("date_text"), 200)
        if title and (start_at or date_text):
            events.append(
                {
                    "title": title,
                    "start_at": start_at,
                    "end_at": _instant(item.get("end_at")),
                    "date_text": date_text,
                    "location": _text(item.get("location"), 300),
                    "attendees": _list(item.get("attendees"), 30, 200),
                    "description": _text(item.get("description")),
                    "tags": _list(item.get("tags"), 8, 60),
                    "source_quote": _quote(item.get("source_quote"), transcript),
                }
            )

    decisions = []
    for item in _objects(raw.get("decisions")):
        description = _text(item.get("description"))
        if description:
            decisions.append(
                {
                    "description": description,
                    "owner": _text(item.get("owner"), 200),
                    "tags": _list(item.get("tags"), 8, 60),
                    "source_quote": _quote(item.get("source_quote"), transcript),
                }
            )

    goals = []
    for item in _objects(raw.get("goals")):
        title = _text(item.get("title"), 300)
        if title:
            goals.append(
                {
                    "title": title,
                    "description": _text(item.get("description")),
                    "target_at": _instant(item.get("target_at")),
                    "target_text": _text(item.get("target_text"), 200),
                    "priority": item.get("priority") if item.get("priority") in _PRIORITIES else "normal",
                    "tags": _list(item.get("tags"), 8, 60),
                    "source_quote": _quote(item.get("source_quote"), transcript),
                }
            )

    people = []
    for item in _objects(raw.get("people")):
        name = _text(item.get("name"), 200)
        if name:
            people.append(
                {
                    "name": name,
                    "role": _text(item.get("role"), 200),
                    "organization": _text(item.get("organization"), 200),
                    "relationship": _text(item.get("relationship"), 200),
                    "source_quote": _quote(item.get("source_quote"), transcript),
                }
            )

    return {
        "title": _text(raw.get("title"), 300) or "Conversación",
        "overview": _text(raw.get("overview"), 6000),
        "emoji": _text(raw.get("emoji"), 16),
        "category": raw.get("category") if raw.get("category") in _CATEGORIES else "other",
        "action_items": tasks,
        "events": events,
        "decisions": decisions,
        "memories": memories,
        "goals": goals,
        "people": people,
    }
