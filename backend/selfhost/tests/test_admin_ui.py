from selfhost.config import settings
from selfhost.db import transaction
from selfhost.profiles import selected_profile


def test_admin_page_and_api_require_admin(client, admin, other):
    page = client.get("/admin")
    assert page.status_code == 200
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert client.get("/admin/assets/admin.js").status_code == 200
    assert client.get("/v1/admin/config").status_code == 401
    assert client.get("/v1/admin/config", headers=other).status_code == 403
    assert client.get("/v1/admin/config", headers=admin).status_code == 200


def test_settings_env_precedence_and_secret_redaction(client, admin, monkeypatch):
    path = "/v1/admin/config/allow_user_model_selection"
    assert client.put(path, headers=admin, json={"value": True}).status_code == 200
    assert settings().allow_user_model_selection is True
    item = next(row for row in client.get("/v1/admin/config", headers=admin).json() if row["key"] == "allow_user_model_selection")
    assert item["source"] == "panel" and item["editable"] is True

    monkeypatch.setenv("OLLOMI_ALLOW_USER_MODEL_SELECTION", "false")
    settings.cache_clear()
    assert settings().allow_user_model_selection is False
    assert client.put(path, headers=admin, json={"value": True}).status_code == 409
    item = next(row for row in client.get("/v1/admin/config", headers=admin).json() if row["key"] == "allow_user_model_selection")
    assert item["source"] == "environment" and item["editable"] is False
    monkeypatch.delenv("OLLOMI_ALLOW_USER_MODEL_SELECTION")
    settings.cache_clear()
    assert settings().allow_user_model_selection is True
    assert client.delete(path, headers=admin).status_code == 200
    assert settings().allow_user_model_selection is False

    assert client.put("/v1/admin/config/database_url", headers=admin, json={"value": "sqlite:///bad"}).status_code == 409
    assert client.put("/v1/admin/config/no_such_setting", headers=admin, json={"value": 1}).status_code == 404
    assert client.put("/v1/admin/config/mcp_access_minutes", headers=admin, json={"value": 1000}).status_code == 422
    assert client.put("/v1/admin/config/voiceprint_api_key", headers=admin, json={"value": "secret-for-testing"}).status_code == 200
    response = client.get("/v1/admin/config", headers=admin)
    assert "secret-for-testing" not in response.text
    secret = next(row for row in response.json() if row["key"] == "voiceprint_api_key")
    assert secret["value"] is None and secret["has_value"] is True


def test_env_admin_password_change_revokes_sessions(client, admin, monkeypatch):
    from selfhost.accounts import seed_admin_from_env

    monkeypatch.setenv("OLLOMI_ADMIN_EMAIL", "admin@test.local")
    monkeypatch.setenv("OLLOMI_ADMIN_PASSWORD", "new-admin-password-123")
    with transaction() as db:
        assert seed_admin_from_env(db) is True
    assert client.get("/v1/auth/me", headers=admin).status_code == 401
    assert client.post("/v1/auth/login", json={"email": "admin@test.local", "password": "admin-password-123"}).status_code == 401
    new_login = client.post("/v1/auth/login", json={"email": "admin@test.local", "password": "new-admin-password-123"})
    assert new_login.status_code == 200
    new_auth = {"Authorization": "Bearer " + new_login.json()["access_token"]}
    assert client.patch("/v1/admin/users/" + new_login.json()["user"]["id"], headers=new_auth,
                        json={"password": "another-password-123"}).status_code == 409
    with transaction() as db:
        assert seed_admin_from_env(db) is False


def test_admin_model_priority_drives_fallback_order(client, admin):
    ids = []
    for name in ("First", "Second"):
        response = client.post("/v1/admin/ai-profiles", headers=admin, json={
            "name": name, "purpose": "chat", "provider": "ollama", "model": name.lower(),
            "base_url": "http://127.0.0.1:11434/v1",
        })
        assert response.status_code == 201
        ids.append(response.json()["id"])
    all_ids = [row["id"] for row in client.get("/v1/admin/ai-profiles", headers=admin).json()
               if row["purpose"] == "chat" and row["enabled"] and row["managed_by"] != "env"]
    ordered = [*ids[::-1], *[profile_id for profile_id in all_ids if profile_id not in ids]]
    response = client.put("/v1/admin/ai-profile-order", headers=admin,
                          json={"purpose": "chat", "ids": ordered})
    assert response.status_code == 200
    user_id = client.get("/v1/auth/me", headers=admin).json()["id"]
    with transaction() as db:
        chain = selected_profile(db, user_id, "chat")
    assert [chain["id"], chain["fallbacks"][0]["id"]] == ids[::-1]
    assert client.put("/v1/admin/ai-profile-order", headers=admin,
                      json={"purpose": "chat", "ids": [ids[0]]}).status_code == 422
