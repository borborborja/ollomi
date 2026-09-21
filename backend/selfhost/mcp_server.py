"""Owner-scoped Streamable HTTP MCP server with local OAuth 2.1 + PKCE."""

import base64
import hashlib
import html
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select, update

from selfhost.config import settings
from selfhost.db import (
    McpApiKey,
    McpOauthClient,
    McpOauthCode,
    McpOauthToken,
    Record,
    User,
    now,
    transaction,
    wire,
)
from selfhost.security import aware, current_user, digest, verify_password

MCP_SCOPE = "ollomi:mcp"
MCP_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", MCP_PROTOCOL_VERSION}
router = APIRouter()


@dataclass(frozen=True)
class McpPrincipal:
    user: User
    scopes: tuple[str, ...]


def _require_enabled() -> None:
    if not settings().mcp_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MCP is disabled")


def _public_url() -> str:
    return settings().mcp_public_url.rstrip("/")


def _mcp_url() -> str:
    return _public_url() + "/mcp"


def _oauth_error(error: str, description: str, code: int = status.HTTP_400_BAD_REQUEST) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"error": error, "error_description": description},
        headers={"Cache-Control": "no-store"},
    )


def _resource_metadata() -> str:
    return _public_url() + "/.well-known/oauth-protected-resource/mcp"


def _unauthorized(*, invalid: bool = False) -> HTTPException:
    parameters = [f'resource_metadata="{_resource_metadata()}"', f'scope="{MCP_SCOPE}"']
    if invalid:
        parameters.insert(0, 'error="invalid_token"')
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "MCP authentication required",
        headers={"WWW-Authenticate": "Bearer " + ", ".join(parameters)},
    )


def _mcp_principal(request: Request) -> McpPrincipal:
    _require_enabled()
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise _unauthorized()
    raw_token = authorization.removeprefix("Bearer ").strip()
    if not raw_token:
        raise _unauthorized(invalid=True)
    with transaction() as db:
        if raw_token.startswith("ollomi_mcp_"):
            row = db.scalar(select(McpApiKey).where(McpApiKey.token_hash == digest(raw_token)).with_for_update())
            if row is None or row.revoked or MCP_SCOPE not in row.scopes:
                raise _unauthorized(invalid=True)
            user = db.get(User, row.user_id)
            if user is None or not user.enabled:
                raise _unauthorized(invalid=True)
            row.last_used_at = now()
            return McpPrincipal(user=user, scopes=tuple(row.scopes))
        row = db.scalar(select(McpOauthToken).where(McpOauthToken.token_hash == digest(raw_token)).with_for_update())
        if (
            row is None
            or row.token_type != "access"
            or row.revoked
            or aware(row.expires_at) <= now()
            or MCP_SCOPE not in row.scopes
        ):
            raise _unauthorized(invalid=True)
        user = db.get(User, row.user_id)
        if user is None or not user.enabled:
            raise _unauthorized(invalid=True)
        return McpPrincipal(user=user, scopes=tuple(row.scopes))


def _key_wire(row: McpApiKey, *, token: str | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "app_id": None,
        "created_at": row.created_at.isoformat(),
        "id": row.id,
        "key_prefix": row.key_prefix,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "name": row.name,
        "scopes": row.scopes,
    }
    if token is not None:
        result["key"] = token
    return result


@router.get("/v1/mcp/keys")
def list_keys(user: User = Depends(current_user)):
    _require_enabled()
    with transaction() as db:
        rows = list(
            db.scalars(
                select(McpApiKey)
                .where(McpApiKey.user_id == user.id, McpApiKey.revoked.is_(False))
                .order_by(McpApiKey.created_at.desc())
            )
        )
        return [_key_wire(row) for row in rows]


@router.post("/v1/mcp/keys")
def create_key(body: dict[str, Any], user: User = Depends(current_user)):
    _require_enabled()
    name = str(body.get("name", "")).strip()
    if not 1 <= len(name) <= 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Key name must contain 1–100 characters")
    token = "ollomi_mcp_" + secrets.token_urlsafe(32)
    with transaction() as db:
        row = McpApiKey(
            user_id=user.id,
            name=name,
            token_hash=digest(token),
            key_prefix=token[:20],
            scopes=[MCP_SCOPE],
        )
        db.add(row)
        db.flush()
        return _key_wire(row, token=token)


@router.delete("/v1/mcp/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(key_id: str, user: User = Depends(current_user)):
    _require_enabled()
    with transaction() as db:
        row = db.get(McpApiKey, key_id)
        if row is None or row.user_id != user.id or row.revoked:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "MCP key not found")
        row.revoked = True
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _valid_redirect_uri(value: str) -> str:
    parsed = urlsplit(value)
    loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if parsed.fragment or parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("redirect_uri is invalid")
    if parsed.scheme == "https" or (parsed.scheme == "http" and loopback):
        return value
    raise ValueError("redirect_uri must use HTTPS or loopback HTTP")


def _scope(value: str | None) -> tuple[str, ...]:
    scopes = tuple(item for item in (value or MCP_SCOPE).split(" ") if item)
    if set(scopes) != {MCP_SCOPE}:
        raise ValueError("only ollomi:mcp scope is supported")
    return scopes


def _pkce_challenge(value: str) -> str:
    if not 43 <= len(value) <= 128 or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~" for character in value
    ):
        raise ValueError("code_challenge is invalid")
    return value


def _pkce_matches(verifier: str, challenge: str) -> bool:
    if not 43 <= len(verifier) <= 128:
        return False
    try:
        encoded = verifier.encode("ascii")
    except UnicodeEncodeError:
        return False
    actual = base64.urlsafe_b64encode(hashlib.sha256(encoded).digest()).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(actual, challenge)


def _authorization_values(values: dict[str, str]) -> tuple[McpOauthClient, str, tuple[str, ...], str]:
    if values.get("response_type") != "code" or values.get("code_challenge_method") != "S256":
        raise ValueError("OAuth client must use Authorization Code with S256 PKCE")
    client_id = values.get("client_id", "")
    redirect_uri = _valid_redirect_uri(values.get("redirect_uri", ""))
    challenge = _pkce_challenge(values.get("code_challenge", ""))
    scopes = _scope(values.get("scope"))
    state = values.get("state", "")
    if len(client_id) > 128 or len(state) > 1024:
        raise ValueError("OAuth request is too long")
    with transaction() as db:
        client = db.scalar(select(McpOauthClient).where(McpOauthClient.client_id == client_id))
        if client is None or client.redirect_uri != redirect_uri:
            raise ValueError("OAuth client or redirect_uri is unknown")
        return client, challenge, scopes, state


def _hidden_fields(values: dict[str, str]) -> str:
    return "".join(
        f'<input type="hidden" name="{html.escape(key)}" value="{html.escape(value)}">'
        for key, value in values.items()
        if key not in {"username", "password"}
    )


@router.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource_metadata():
    _require_enabled()
    return JSONResponse(
        {
            "resource": _mcp_url(),
            "authorization_servers": [_public_url()],
            "scopes_supported": [MCP_SCOPE],
            "bearer_methods_supported": ["header"],
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.get("/.well-known/oauth-authorization-server")
def authorization_server_metadata():
    _require_enabled()
    base = _public_url()
    return JSONResponse(
        {
            "issuer": base,
            "authorization_endpoint": base + "/oauth/authorize",
            "token_endpoint": base + "/oauth/token",
            "revocation_endpoint": base + "/oauth/revoke",
            "registration_endpoint": base + "/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": ["none"],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": [MCP_SCOPE],
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.post("/oauth/register", status_code=status.HTTP_201_CREATED)
async def register_oauth_client(request: Request):
    _require_enabled()
    from selfhost.rate_limit import limit

    limit("mcp-register:" + (request.client.host if request.client else "unknown"), 10, 60)
    try:
        body = await request.json()
        redirect_uris = body.get("redirect_uris") if isinstance(body, dict) else None
        if not isinstance(redirect_uris, list) or len(redirect_uris) != 1 or not isinstance(redirect_uris[0], str):
            raise ValueError("exactly one redirect_uri is required")
        if body.get("token_endpoint_auth_method", "none") != "none":
            raise ValueError("only public PKCE clients are supported")
        redirect_uri = _valid_redirect_uri(redirect_uris[0])
        name = str(body.get("client_name") or "Ollomi MCP client").strip()
        if not 1 <= len(name) <= 100:
            raise ValueError("client_name must contain 1–100 characters")
    except (TypeError, ValueError):
        return _oauth_error("invalid_client_metadata", "The OAuth client registration is invalid")
    client_id = "ollomi_" + secrets.token_urlsafe(24)
    with transaction() as db:
        row = McpOauthClient(client_id=client_id, name=name, redirect_uri=redirect_uri)
        db.add(row)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "client_id": client_id,
            "client_name": name,
            "redirect_uris": [redirect_uri],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/oauth/authorize")
def oauth_authorize_form(request: Request):
    _require_enabled()
    values = {key: value for key, value in request.query_params.items()}
    try:
        client, _challenge, _scopes, _state = _authorization_values(values)
    except ValueError as error:
        return HTMLResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=f"<h1>Authorization failed</h1><p>{html.escape(str(error))}</p>",
        )
    return HTMLResponse(
        content=(
            "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><title>Authorize Ollomi</title>"
            f"<main><h1>Connect {html.escape(client.name)} to Ollomi</h1>"
            "<p>This grants read-only access to your Ollomi conversations, memories and tasks. "
            "You can revoke it later in Developer settings.</p>"
            f"<form method=\"post\" action=\"/oauth/authorize\">{_hidden_fields(values)}"
            "<label>Email <input required name=\"username\" autocomplete=\"username\"></label>"
            "<label>Password <input required type=\"password\" name=\"password\" autocomplete=\"current-password\"></label>"
            "<button type=\"submit\">Authorize</button></form></main></html>"
        ),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/oauth/authorize")
async def oauth_authorize_submit(request: Request):
    _require_enabled()
    from selfhost.rate_limit import limit

    limit("mcp-authorize:" + (request.client.host if request.client else "unknown"), 10, 60)
    form = await request.form()
    values = {key: str(value) for key, value in form.items()}
    try:
        client, challenge, scopes, state_value = _authorization_values(values)
        username = values.get("username", "").strip().lower()
        password = values.get("password", "")
        if not username or len(username) > 254 or not password or len(password) > 1024:
            raise ValueError("Email or password is invalid")
        with transaction() as db:
            user = db.scalar(select(User).where(User.email == username))
            if user is None or not user.enabled or not verify_password(password, user.password_hash):
                raise ValueError("Email or password is invalid")
            code = "ollomi_code_" + secrets.token_urlsafe(32)
            db.add(
                McpOauthCode(
                    client_id=client.id,
                    user_id=user.id,
                    code_hash=digest(code),
                    code_challenge=challenge,
                    scopes=list(scopes),
                    expires_at=now() + timedelta(minutes=5),
                )
            )
    except ValueError as error:
        return HTMLResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=f"<h1>Authorization failed</h1><p>{html.escape(str(error))}</p>",
        )
    parsed = urlsplit(client.redirect_uri)
    query = [*parse_qsl(parsed.query, keep_blank_values=True), ("code", code)]
    if state_value:
        query.append(("state", state_value))
    location = urlunsplit(parsed._replace(query=urlencode(query)))
    return RedirectResponse(location, status_code=status.HTTP_303_SEE_OTHER, headers={"Cache-Control": "no-store"})


def _issue_tokens(db, client: McpOauthClient, user: User, scopes: tuple[str, ...]) -> dict[str, object]:
    access = "ollomi_oauth_" + secrets.token_urlsafe(32)
    refresh = "ollomi_refresh_" + secrets.token_urlsafe(40)
    db.add_all(
        [
            McpOauthToken(
                client_id=client.id,
                user_id=user.id,
                token_hash=digest(access),
                token_type="access",
                scopes=list(scopes),
                expires_at=now() + timedelta(minutes=settings().mcp_access_minutes),
            ),
            McpOauthToken(
                client_id=client.id,
                user_id=user.id,
                token_hash=digest(refresh),
                token_type="refresh",
                scopes=list(scopes),
                expires_at=now() + timedelta(days=settings().mcp_refresh_days),
            ),
        ]
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": settings().mcp_access_minutes * 60,
        "scope": " ".join(scopes),
    }


@router.post("/oauth/token")
async def oauth_token(request: Request):
    _require_enabled()
    form = await request.form()
    values = {key: str(value) for key, value in form.items()}
    client_id = values.get("client_id", "")
    grant_type = values.get("grant_type", "")
    with transaction() as db:
        client = db.scalar(select(McpOauthClient).where(McpOauthClient.client_id == client_id))
        if client is None:
            return _oauth_error("invalid_client", "Unknown OAuth client", status.HTTP_401_UNAUTHORIZED)
        if grant_type == "authorization_code":
            try:
                code = values["code"]
                redirect_uri = _valid_redirect_uri(values["redirect_uri"])
                verifier = values["code_verifier"]
            except (KeyError, ValueError):
                return _oauth_error("invalid_request", "Invalid authorization-code request")
            row = db.scalar(select(McpOauthCode).where(McpOauthCode.code_hash == digest(code)).with_for_update())
            if (
                row is None
                or row.client_id != client.id
                or client.redirect_uri != redirect_uri
                or aware(row.expires_at) <= now()
                or not _pkce_matches(verifier, row.code_challenge)
            ):
                return _oauth_error("invalid_grant", "Authorization code is invalid or expired")
            user = db.get(User, row.user_id)
            if user is None or not user.enabled:
                return _oauth_error("invalid_grant", "Account is unavailable")
            scopes = tuple(row.scopes)
            db.delete(row)
            return _issue_tokens(db, client, user, scopes)
        if grant_type == "refresh_token":
            raw_refresh = values.get("refresh_token", "")
            row = db.scalar(
                select(McpOauthToken).where(McpOauthToken.token_hash == digest(raw_refresh)).with_for_update()
            )
            if (
                row is None
                or row.client_id != client.id
                or row.token_type != "refresh"
                or row.revoked
                or aware(row.expires_at) <= now()
            ):
                return _oauth_error("invalid_grant", "Refresh token is invalid or expired")
            user = db.get(User, row.user_id)
            if user is None or not user.enabled:
                return _oauth_error("invalid_grant", "Account is unavailable")
            row.revoked = True
            return _issue_tokens(db, client, user, tuple(row.scopes))
    return _oauth_error("unsupported_grant_type", "Grant type is not supported")


@router.post("/oauth/revoke", status_code=status.HTTP_200_OK)
async def oauth_revoke(request: Request):
    _require_enabled()
    form = await request.form()
    raw_token = str(form.get("token", ""))
    if raw_token:
        with transaction() as db:
            db.execute(update(McpOauthToken).where(McpOauthToken.token_hash == digest(raw_token)).values(revoked=True))
    return Response(status_code=status.HTTP_200_OK, headers={"Cache-Control": "no-store"})


def _mcp_conversation(row: Record) -> dict[str, object]:
    value = wire(row)
    value.pop("file_ids", None)
    value.pop("audio_files", None)
    return value


def _tool_list() -> list[dict[str, object]]:
    return [
        {
            "name": "ollomi_list_conversations",
            "description": "List recent conversations for the authenticated Ollomi account. Audio files are never returned.",
            "inputSchema": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "ollomi_get_conversation",
            "description": "Read one conversation, its transcript and structured extraction. Audio files are never returned.",
            "inputSchema": {
                "type": "object",
                "properties": {"conversation_id": {"type": "string"}},
                "required": ["conversation_id"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "ollomi_list_memories",
            "description": "List recent personal memories for the authenticated Ollomi account.",
            "inputSchema": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
        {
            "name": "ollomi_list_tasks",
            "description": "List recent action items for the authenticated Ollomi account.",
            "inputSchema": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        },
    ]


def _tool_result(value: object) -> dict[str, object]:
    import json

    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}], "structuredContent": value}


def _mcp_error(request_id: object, code: int, message: str) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _mcp_response(payload: object, user: User) -> dict[str, object] | None:
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        return _mcp_error(None, -32600, "Invalid Request")
    request_id, method = payload.get("id"), payload.get("method")
    params = payload.get("params", {})
    if not isinstance(method, str) or not isinstance(params, dict):
        return _mcp_error(request_id, -32600, "Invalid Request")
    if method == "initialize":
        version = params.get("protocolVersion")
        if version not in SUPPORTED_PROTOCOL_VERSIONS:
            return _mcp_error(request_id, -32602, "Unsupported protocol version")
        result: dict[str, object] = {
            "protocolVersion": version,
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            "serverInfo": {"name": "ollomi", "version": "0.3.3"},
            "instructions": "Ollomi is a self-hosted personal audio and memory service.",
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": _tool_list()}
    elif method in {"resources/list", "prompts/list"}:
        result = {"resources" if method == "resources/list" else "prompts": []}
    elif method == "tools/call":
        name, arguments = params.get("name"), params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return _mcp_error(request_id, -32602, "Invalid tool arguments")
        limit = arguments.get("limit", 20)
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            return _mcp_error(request_id, -32602, "limit must be an integer between 1 and 100")
        with transaction() as db:
            if name == "ollomi_list_conversations":
                rows = list(
                    db.scalars(
                        select(Record)
                        .where(Record.user_id == user.id, Record.kind == "conversation")
                        .order_by(Record.created_at.desc())
                        .limit(limit)
                    )
                )
                result = _tool_result({"conversations": [_mcp_conversation(row) for row in rows]})
            elif name == "ollomi_get_conversation":
                conversation_id = arguments.get("conversation_id")
                if not isinstance(conversation_id, str):
                    return _mcp_error(request_id, -32602, "conversation_id is required")
                row = db.get(Record, conversation_id)
                if row is None or row.user_id != user.id or row.kind != "conversation":
                    return _mcp_error(request_id, -32602, "Conversation not found")
                result = _tool_result({"conversation": _mcp_conversation(row)})
            elif name in {"ollomi_list_memories", "ollomi_list_tasks"}:
                kind = "memory" if name == "ollomi_list_memories" else "task"
                rows = list(
                    db.scalars(
                        select(Record)
                        .where(Record.user_id == user.id, Record.kind == kind)
                        .order_by(Record.created_at.desc())
                        .limit(limit)
                    )
                )
                result = _tool_result({kind + "s": [wire(row) for row in rows]})
            else:
                return _mcp_error(request_id, -32602, "Unknown tool")
    elif method.startswith("notifications/"):
        return None
    else:
        return _mcp_error(request_id, -32601, "Method not found")
    if request_id is None:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


@router.post("/mcp")
async def mcp(request: Request, principal: McpPrincipal = Depends(_mcp_principal)):
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse(_mcp_error(None, -32700, "Parse error"), status_code=status.HTTP_400_BAD_REQUEST)
    response = _mcp_response(payload, principal.user)
    if response is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return JSONResponse(response, headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION, "Cache-Control": "no-store"})
