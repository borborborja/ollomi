from io import BytesIO

import pytest
from PIL import Image


def _tile():
    output = BytesIO()
    Image.new("RGB", (256, 256), "#67ab69").save(output, format="PNG")
    return output.getvalue()


def test_static_map_requires_auth_and_rejects_bad_coordinates(client, admin):
    path = "/v1/static-map?pins=42.27,2.93&width=320&height=200"
    assert client.get(path).status_code == 401
    assert client.get(path.replace("42.27", "nan"), headers=admin).status_code == 400
    assert client.get(path.replace("42.27", "91"), headers=admin).status_code == 400


def test_static_map_renders_osm_tiles_without_a_key(client, admin, monkeypatch):
    from selfhost import static_map

    fetched = []

    def fake_tile(z, x, y):
        fetched.append((z, x, y))
        return _tile()

    monkeypatch.setattr(static_map, "_fetch_tile", fake_tile)
    response = client.get(
        "/v1/static-map?pins=42.2670,2.9290|42.2680,2.9310&width=320&height=200",
        headers=admin,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert fetched
    with Image.open(BytesIO(response.content)) as image:
        assert image.size == (320, 200)
        assert image.getpixel((0, 0)) == (103, 171, 105)


def test_static_map_has_a_deterministic_offline_failure(client, admin, monkeypatch):
    from selfhost import static_map

    monkeypatch.setattr(static_map, "_fetch_tile", lambda *_: None)
    fallbacks = []
    monkeypatch.setattr(static_map, "record_fallback", lambda **event: fallbacks.append(event))
    response = client.get("/v1/static-map?pins=42.2670,2.9290&width=320&height=200", headers=admin)
    assert response.status_code == 502
    assert "temporarily unavailable" in response.json()["detail"]
    assert fallbacks == [
        {
            "purpose": "static_map",
            "from_profile": "configured_osm_tiles",
            "to_profile": "app_pin_canvas",
            "reason": "tiles_unavailable",
            "outcome": "degraded",
        }
    ]


def test_osm_tile_cache_prevents_a_second_network_fetch(client, monkeypatch):
    from selfhost import static_map

    calls = []

    class Response:
        headers = {"content-type": "image/png"}
        content = _tile()

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(static_map.httpx, "get", fake_get)
    first = static_map._fetch_tile(12, 2081, 1520)
    second = static_map._fetch_tile(12, 2081, 1520)
    assert first == second == Response.content
    assert len(calls) == 1
    assert calls[0][0] == "https://tile.openstreetmap.org/12/2081/1520.png"
    assert "Ollomi" in calls[0][1]["headers"]["User-Agent"]


def test_tile_cache_is_separated_by_configured_provider(client, monkeypatch):
    from selfhost import static_map
    from selfhost.config import settings

    public_path = static_map._tile_path(12, 2081, 1520)
    monkeypatch.setenv("OLLOMI_MAP_TILE_URL", "http://tiles.local/{z}/{x}/{y}.png")
    settings.cache_clear()
    local_path = static_map._tile_path(12, 2081, 1520)
    assert public_path != local_path

    requested = []

    class Response:
        headers = {"content-type": "image/png"}
        content = _tile()

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        requested.append(url)
        return Response()

    monkeypatch.setattr(static_map.httpx, "get", fake_get)
    assert static_map._fetch_tile(12, 2081, 1520) == Response.content
    assert requested == ["http://tiles.local/12/2081/1520.png"]


def test_map_tile_url_must_be_a_safe_template(client, monkeypatch):
    from selfhost.config import settings

    monkeypatch.setenv("OLLOMI_MAP_TILE_URL", "file:///etc/{z}/{x}/{y}.png")
    settings.cache_clear()
    with pytest.raises(ValueError, match="OLLOMI_MAP_TILE_URL"):
        settings().validate_runtime()
