"""Explicit local exports and MCP calls to administrator-approved servers."""

import json
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from selfhost.db import Record, emit, ident, now, transaction, wire
from selfhost.profiles import validate_url
from selfhost.security import administrator, current_user, seal, unseal

router = APIRouter()


class ConnectorInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["webdav", "caldav", "webhook", "mcp"]
    base_url: str = Field(max_length=2000)
    username: str = Field(default="", max_length=200)
    secret: str | None = Field(default=None, max_length=4096)
    enabled: bool = True


def public(row):
    return {
        "id": row.id,
        **{k: v for k, v in row.data.items() if k != "encrypted_secret"},
        "has_secret": bool(row.data.get("encrypted_secret")),
    }


@router.get("/v1/local/integrations")
def list_integrations(user=Depends(current_user)):
    with transaction() as db:
        rows = db.scalars(select(Record).where(Record.kind == "connector"))
        return [public(row) for row in rows if user.admin or row.data["enabled"]]


@router.post("/v1/admin/integrations", status_code=201)
def add_connector(body: ConnectorInput, admin=Depends(administrator)):
    url = validate_url(body.base_url, False)
    with transaction() as db:
        row = Record(
            id=ident(),
            user_id=admin.id,
            kind="connector",
            data={
                **body.model_dump(exclude={"secret", "base_url"}),
                "base_url": url,
                "encrypted_secret": seal(body.secret or ""),
            },
        )
        db.add(row)
        db.flush()
        return public(row)


@router.put("/v1/admin/integrations/{connector_id}")
def edit_connector(
    connector_id: str, body: ConnectorInput, admin=Depends(administrator)
):
    url = validate_url(body.base_url, False)
    with transaction() as db:
        row = db.get(Record, connector_id)
        if not row or row.kind != "connector":
            raise HTTPException(404, "Connector not found")
        row.data = {
            **body.model_dump(exclude={"secret", "base_url"}),
            "base_url": url,
            "encrypted_secret": seal(body.secret)
            if body.secret is not None
            else row.data["encrypted_secret"],
        }
        return public(row)


def connector_settings(connector_id, expected=None):
    with transaction() as db:
        row = db.get(Record, connector_id)
        if (
            not row
            or row.kind != "connector"
            or not row.data["enabled"]
            or (expected and row.data["kind"] != expected)
        ):
            raise HTTPException(404, "Connector not available")
        data = dict(row.data)
    validate_url(data["base_url"], False)
    return data


def connector_client(data):
    secret = unseal(data.get("encrypted_secret", ""))
    return httpx.Client(
        timeout=60,
        trust_env=False,
        follow_redirects=False,
        auth=(data["username"], secret) if data.get("username") else None,
        headers={"Authorization": "Bearer " + secret}
        if secret and not data.get("username")
        else {},
    )


def export_data(uid):
    with transaction() as db:
        return [
            dict(kind=row.kind, **wire(row))
            for row in db.scalars(
                select(Record).where(
                    Record.user_id == uid,
                    Record.kind.in_(
                        ["conversation", "memory", "task", "person", "folder", "goal", "decision", "calendar_event"]
                    ),
                )
            )
        ]


def ical_escape(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("\r", "")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def task_ical(task):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Ollomi//Local Tasks//ES",
        "BEGIN:VTODO",
        "UID:" + task["id"] + "@ollomi",
        "DTSTAMP:" + now().strftime("%Y%m%dT%H%M%SZ"),
        "SUMMARY:" + ical_escape(task["description"]),
        "STATUS:" + ("COMPLETED" if task.get("completed") else "NEEDS-ACTION"),
    ]
    if task.get("due_at"):
        due = datetime.fromisoformat(task["due_at"].replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
        lines.append("DUE:" + due.strftime("%Y%m%dT%H%M%SZ"))
    lines += ["END:VTODO", "END:VCALENDAR"]
    # Fold at UTF-8 character boundaries, with physical lines no longer than 75 octets.
    folded = []
    for line in lines:
        chunk = ""
        for char in line:
            if len((chunk + char).encode()) > 74:
                folded.append(chunk)
                chunk = " "
            chunk += char
        folded.append(chunk)
    return "\r\n".join(folded) + "\r\n"


@router.post("/v1/local/integrations/{connector_id}/export")
def export(connector_id: str, user=Depends(current_user)):
    data = connector_settings(connector_id)
    if data["kind"] == "mcp":
        raise HTTPException(422, "MCP uses explicit tool calls")
    records = export_data(user.id)
    try:
        with connector_client(data) as client:
            if data["kind"] == "webdav":
                response = client.put(
                    data["base_url"].rstrip("/") + "/" + user.id + ".json",
                    content=json.dumps(
                        {"records": records}, ensure_ascii=False
                    ).encode(),
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
            elif data["kind"] == "webhook":
                response = client.post(
                    data["base_url"],
                    json={
                        "event": "ollomi.export",
                        "user_id": user.id,
                        "records": records,
                    },
                )
                response.raise_for_status()
            else:
                for task in (r for r in records if r["kind"] == "task"):
                    response = client.put(
                        data["base_url"].rstrip("/") + "/" + task["id"] + ".ics",
                        content=task_ical(task).encode(),
                        headers={"Content-Type": "text/calendar; charset=utf-8"},
                    )
                    response.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(
            502, "Local export failed; repeating WebDAV/CalDAV export is idempotent"
        ) from None
    with transaction() as db:
        emit(db, user.id, "export_completed", {"connector_id": connector_id})
    return {"status": "ok"}


def mcp_result(response):
    response.raise_for_status()
    if "text/event-stream" in response.headers.get("content-type", ""):
        values = [
            json.loads(line[5:])
            for line in response.text.splitlines()
            if line.startswith("data:")
        ]
        payload = next(
            (value for value in values if "result" in value or "error" in value), {}
        )
    else:
        payload = response.json()
    if "error" in payload or "result" not in payload:
        raise HTTPException(502, "MCP server rejected the request")
    return payload["result"]


def mcp_call(data, method, params):
    try:
        with connector_client(data) as client:
            headers = {
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-03-26",
            }

            def post(value):
                return client.post(data["base_url"], json=value, headers=headers)

            init = post(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "ollomi", "version": "0.1.0"},
                    },
                }
            )
            negotiated = mcp_result(init)
            headers["MCP-Protocol-Version"] = negotiated["protocolVersion"]
            if init.headers.get("Mcp-Session-Id"):
                headers["Mcp-Session-Id"] = init.headers["Mcp-Session-Id"]
            post(
                {"jsonrpc": "2.0", "method": "notifications/initialized"}
            ).raise_for_status()
            result = mcp_result(
                post({"jsonrpc": "2.0", "id": 2, "method": method, "params": params})
            )
            if "Mcp-Session-Id" in headers:
                client.delete(data["base_url"], headers=headers)
            return result
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(502, "MCP connection failed") from None


@router.get("/v1/local/integrations/{connector_id}/tools")
def tools(connector_id: str, user=Depends(current_user)):
    return mcp_call(connector_settings(connector_id, "mcp"), "tools/list", {})


class ToolCall(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    arguments: dict = Field(default_factory=dict)


@router.post("/v1/local/integrations/{connector_id}/call")
def call(connector_id: str, body: ToolCall, user=Depends(current_user)):
    return mcp_call(
        connector_settings(connector_id, "mcp"), "tools/call", body.model_dump()
    )
