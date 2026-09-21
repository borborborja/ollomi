import base64
import hashlib
from urllib.parse import parse_qs, urlsplit


def _challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def _mcp(client, token, payload):
    return client.post("/mcp", headers={"Authorization": "Bearer " + token}, json=payload)


def test_personal_mcp_key_is_owner_scoped_and_revocable(client, admin, other):
    conversation = client.post("/v1/conversations", headers=admin, json={}).json()["conversation"]
    assert client.post("/v1/conversations", headers=other, json={}).status_code == 200

    created = client.post("/v1/mcp/keys", headers=admin, json={"name": "Claude Desktop"})
    assert created.status_code == 200
    key = created.json()
    assert key["key"].startswith("ollomi_mcp_")
    assert key["key"] not in client.get("/v1/mcp/keys", headers=admin).text

    listed = _mcp(
        client,
        key["key"],
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "ollomi_list_conversations"}},
    )
    assert listed.status_code == 200
    conversations = listed.json()["result"]["structuredContent"]["conversations"]
    assert [item["id"] for item in conversations] == [conversation["id"]]
    assert "file_ids" not in conversations[0]

    assert client.delete("/v1/mcp/keys/" + key["id"], headers=admin).status_code == 204
    assert _mcp(client, key["key"], {"jsonrpc": "2.0", "id": 2, "method": "ping"}).status_code == 401


def test_mcp_oauth_pkce_flow_and_revocation(client):
    server_info = client.get("/v1/server-info").json()
    assert "mcp" in server_info["capabilities"]
    assert server_info["mcp_url"] == "https://ollomi.test/mcp"
    resource = client.get("/.well-known/oauth-protected-resource/mcp")
    assert resource.status_code == 200
    assert resource.json()["resource"] == "https://ollomi.test/mcp"

    registration = client.post(
        "/oauth/register",
        json={"client_name": "MCP test client", "redirect_uris": ["http://127.0.0.1:48231/callback"]},
    )
    assert registration.status_code == 201
    client_id = registration.json()["client_id"]
    verifier = "v" * 43
    authorization = client.post(
        "/oauth/authorize",
        data={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "http://127.0.0.1:48231/callback",
            "scope": "ollomi:mcp",
            "state": "state-value",
            "code_challenge_method": "S256",
            "code_challenge": _challenge(verifier),
            "username": "admin@test.local",
            "password": "admin-password-123",
        },
        follow_redirects=False,
    )
    assert authorization.status_code == 303
    callback = urlsplit(authorization.headers["location"])
    query = parse_qs(callback.query)
    assert callback.hostname == "127.0.0.1"
    assert query["state"] == ["state-value"]

    tokens = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": "http://127.0.0.1:48231/callback",
            "code": query["code"][0],
            "code_verifier": verifier,
        },
    )
    assert tokens.status_code == 200
    access_token = tokens.json()["access_token"]
    refresh_token = tokens.json()["refresh_token"]
    assert access_token.startswith("ollomi_oauth_")
    tools = _mcp(client, access_token, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert tools.status_code == 200
    assert {tool["name"] for tool in tools.json()["result"]["tools"]} >= {
        "ollomi_list_conversations",
        "ollomi_list_tasks",
    }

    refreshed = client.post(
        "/oauth/token",
        data={"grant_type": "refresh_token", "client_id": client_id, "refresh_token": refresh_token},
    )
    assert refreshed.status_code == 200
    refreshed_access = refreshed.json()["access_token"]
    assert refreshed_access != access_token
    assert client.post(
        "/oauth/token",
        data={"grant_type": "refresh_token", "client_id": client_id, "refresh_token": refresh_token},
    ).status_code == 400

    assert client.post("/oauth/revoke", data={"token": refreshed_access}).status_code == 200
    assert _mcp(client, refreshed_access, {"jsonrpc": "2.0", "id": 4, "method": "ping"}).status_code == 401


def test_mcp_oauth_refuses_unsafe_or_unregistered_redirects(client):
    unsafe = client.post(
        "/oauth/register",
        json={"client_name": "unsafe", "redirect_uris": ["http://example.test/callback"]},
    )
    assert unsafe.status_code == 400

    registration = client.post(
        "/oauth/register",
        json={"client_name": "safe", "redirect_uris": ["https://client.example.test/callback"]},
    )
    assert registration.status_code == 201
    client_id = registration.json()["client_id"]
    rejected = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://different.example.test/callback",
            "scope": "ollomi:mcp",
            "code_challenge_method": "S256",
            "code_challenge": _challenge("v" * 43),
        },
    )
    assert rejected.status_code == 400


def test_mcp_oauth_code_requires_the_registered_client_and_valid_pkce(client):
    first = client.post(
        "/oauth/register",
        json={"client_name": "first", "redirect_uris": ["http://127.0.0.1:48231/callback"]},
    ).json()
    second = client.post(
        "/oauth/register",
        json={"client_name": "second", "redirect_uris": ["http://127.0.0.1:48232/callback"]},
    ).json()
    verifier = "v" * 43
    authorization = client.post(
        "/oauth/authorize",
        data={
            "response_type": "code",
            "client_id": first["client_id"],
            "redirect_uri": "http://127.0.0.1:48231/callback",
            "scope": "ollomi:mcp",
            "code_challenge_method": "S256",
            "code_challenge": _challenge(verifier),
            "username": "admin@test.local",
            "password": "admin-password-123",
        },
        follow_redirects=False,
    )
    code = parse_qs(urlsplit(authorization.headers["location"]).query)["code"][0]
    stolen_client = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": second["client_id"],
            "redirect_uri": "http://127.0.0.1:48232/callback",
            "code": code,
            "code_verifier": verifier,
        },
    )
    assert stolen_client.status_code == 400
    wrong_verifier = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": first["client_id"],
            "redirect_uri": "http://127.0.0.1:48231/callback",
            "code": code,
            "code_verifier": "w" * 43,
        },
    )
    assert wrong_verifier.status_code == 400
    assert client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": first["client_id"],
            "redirect_uri": "http://127.0.0.1:48231/callback",
            "code": code,
            "code_verifier": verifier,
        },
    ).status_code == 200


def test_password_reset_revokes_mcp_credentials(client, admin, other):
    key = client.post("/v1/mcp/keys", headers=other, json={"name": "temporary"}).json()["key"]
    other_user = client.get("/v1/auth/me", headers=other).json()
    assert (
        client.patch(
            "/v1/admin/users/" + other_user["id"],
            headers=admin,
            json={"password": "replaced-password-123"},
        ).status_code
        == 200
    )
    assert _mcp(client, key, {"jsonrpc": "2.0", "id": 5, "method": "ping"}).status_code == 401
