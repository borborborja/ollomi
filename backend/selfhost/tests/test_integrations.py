import httpx
import respx


def test_only_admin_can_approve_connector_and_export_is_owner_scoped(
    client, admin, other
):
    config = {
        "name": "Local archive",
        "kind": "webdav",
        "base_url": "http://127.0.0.1:9000/dav",
        "secret": "secret-value",
    }
    assert (
        client.post("/v1/admin/integrations", headers=other, json=config).status_code
        == 403
    )
    response = client.post("/v1/admin/integrations", headers=admin, json=config)
    assert response.status_code == 201
    connector = response.json()["id"]
    assert "secret-value" not in response.text
    assert (
        "secret-value" not in client.get("/v1/local/integrations", headers=other).text
    )
    client.post(
        "/v3/memories", headers=admin, json={"content": "private administrator note"}
    )
    client.post("/v3/memories", headers=other, json={"content": "my own note"})
    with respx.mock as mock:
        route = mock.put(url__regex=r"http://127.0.0.1:9000/dav/.*").mock(
            return_value=httpx.Response(201)
        )
        assert (
            client.post(
                f"/v1/local/integrations/{connector}/export", headers=other
            ).status_code
            == 200
        )
        assert b"my own note" in route.calls[0].request.content
        assert b"private administrator note" not in route.calls[0].request.content
        assert route.calls[0].request.headers["authorization"] == "Bearer secret-value"


def test_caldav_escaping_and_utf8_folding():
    from selfhost.integrations import task_ical

    value = task_ical(
        {
            "id": "x",
            "description": "á" * 150 + "\nBEGIN:VEVENT;injected,",
            "due_at": "2026-09-15T10:00:00+02:00",
        }
    )
    assert "DUE:20260915T080000Z" in value
    assert "\\nBEGIN:VEVENT\\;injected\\," in value
    assert all(len(line.encode()) <= 75 for line in value.split("\r\n"))


def test_mcp_initialize_session_and_call(client, admin):
    response = client.post(
        "/v1/admin/integrations",
        headers=admin,
        json={"name": "MCP", "kind": "mcp", "base_url": "http://127.0.0.1:9000/mcp"},
    )
    connector = response.json()["id"]
    requests = []

    def handler(request):
        import json

        if request.method == "DELETE":
            return httpx.Response(204)
        body = json.loads(request.content)
        requests.append(body)
        if body["method"] == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"protocolVersion": "2025-03-26"},
                },
                headers={"Mcp-Session-Id": "test-session"},
            )
        assert request.headers["Mcp-Session-Id"] == "test-session"
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "tools": [{"name": "local-tool", "inputSchema": {"type": "object"}}]
                },
            },
        )

    with respx.mock as mock:
        mock.route(url="http://127.0.0.1:9000/mcp").mock(side_effect=handler)
        result = client.get(f"/v1/local/integrations/{connector}/tools", headers=admin)
        assert result.status_code == 200
        assert result.json()["tools"][0]["name"] == "local-tool"
    assert [r["method"] for r in requests] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
    ]
