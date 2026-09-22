"""Small authenticated OSM preview renderer with a persistent tile cache.

Only tiles visible in the requested preview are fetched. Public OSM tiles are
cached for at least seven days and identified by an Ollomi User-Agent. An
administrator may instead point OLLOMI_MAP_TILE_URL at their own tile server.
"""

from hashlib import sha256
from io import BytesIO
from math import asinh, floor, isfinite, pi, tan
from time import time
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from selfhost.config import settings
from selfhost.observability import record_fallback
from selfhost.rate_limit import limit
from selfhost.security import current_user

router = APIRouter()

_TILE_SIZE = 256
_CACHE_SECONDS = 7 * 24 * 60 * 60
_MAX_PINS = 50
_MAX_IMAGE_PX = 512
_USER_AGENT = "Ollomi/1.0 (+https://github.com/borborborja/ollomi)"


def parse_pins(value):
    if not value:
        raise HTTPException(400, "At least one map pin is required")
    if len(value) > 2_000:
        raise HTTPException(400, "Too many map pins")
    result = []
    for pair in value.split("|"):
        parts = pair.split(",")
        if len(parts) != 2:
            raise HTTPException(400, "Invalid map pin")
        try:
            lat, lng = (float(part) for part in parts)
        except ValueError:
            raise HTTPException(400, "Invalid map pin") from None
        if not isfinite(lat) or not isfinite(lng) or not -85.0511 <= lat <= 85.0511 or not -180 <= lng <= 180:
            raise HTTPException(400, "Map pin out of bounds")
        point = (round(lat, 4), round(lng, 4))
        if point not in result:
            result.append(point)
        if len(result) > _MAX_PINS:
            raise HTTPException(400, "Too many map pins")
    return result


def _project(lat, lng, zoom):
    world = _TILE_SIZE * (2**zoom)
    latitude = lat * pi / 180
    return ((lng + 180) / 360 * world, (1 - asinh(tan(latitude)) / pi) / 2 * world)


def _frame(pins, width, height):
    margin = min(35, width // 4, height // 4)
    for zoom in range(17, -1, -1):
        points = [_project(lat, lng, zoom) for lat, lng in pins]
        world = _TILE_SIZE * 2**zoom
        xs = [point[0] for point in points]
        if max(xs) - min(xs) > world / 2:
            points = [(x + world if x < world / 2 else x, y) for x, y in points]
        xs, ys = zip(*points)
        if max(xs) - min(xs) <= width - 2 * margin and max(ys) - min(ys) <= height - 2 * margin:
            break
    return zoom, points, (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def _tile_path(zoom, x, y):
    provider = sha256(settings().map_tile_url.encode()).hexdigest()[:12]
    return settings().data_dir / "map-tiles" / provider / str(zoom) / str(x) / f"{y}.png"


def _fetch_tile(zoom, x, y):
    path = _tile_path(zoom, x, y)
    try:
        if path.is_file() and time() - path.stat().st_mtime < _CACHE_SECONDS:
            return path.read_bytes()
    except OSError:
        pass

    url = settings().map_tile_url.format(z=zoom, x=x, y=y)
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=5,
            follow_redirects=False,
            trust_env=False,
        )
        response.raise_for_status()
        if not response.headers.get("content-type", "").startswith("image/png") or len(response.content) > 1_000_000:
            return None
        with Image.open(BytesIO(response.content)) as image:
            if image.size != (_TILE_SIZE, _TILE_SIZE):
                return None
            image.verify()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix("." + uuid4().hex + ".tmp")
        temporary.write_bytes(response.content)
        temporary.replace(path)
        return response.content
    except (httpx.HTTPError, OSError, UnidentifiedImageError, ValueError):
        # A stale tile is still better than a blank preview when OSM is down.
        try:
            return path.read_bytes() if path.is_file() else None
        except OSError:
            return None


def render_map(pins, width, height):
    factor = min(1.0, _MAX_IMAGE_PX / width, _MAX_IMAGE_PX / height)
    width, height = max(64, int(width * factor)), max(64, int(height * factor))
    zoom, points, center_x, center_y = _frame(pins, width, height)
    left, top = center_x - width / 2, center_y - height / 2
    image = Image.new("RGB", (width, height), "#e7e5e1")
    first_x, last_x = floor(left / _TILE_SIZE), floor((left + width - 1) / _TILE_SIZE)
    first_y, last_y = floor(top / _TILE_SIZE), floor((top + height - 1) / _TILE_SIZE)

    for tile_x in range(first_x, last_x + 1):
        for tile_y in range(first_y, last_y + 1):
            if not 0 <= tile_y < 2**zoom:
                continue
            content = _fetch_tile(zoom, tile_x % (2**zoom), tile_y)
            if content is None:
                return None
            try:
                with Image.open(BytesIO(content)) as tile:
                    image.paste(
                        tile.convert("RGB"), (round(tile_x * _TILE_SIZE - left), round(tile_y * _TILE_SIZE - top))
                    )
            except (OSError, UnidentifiedImageError, ValueError):
                return None

    draw = ImageDraw.Draw(image)
    for x, y in points:
        px, py = round(x - left), round(y - top)
        draw.ellipse((px - 7, py - 7, px + 7, py + 7), fill="white", outline="black", width=2)

    attribution = "© OpenStreetMap contributors"
    font = ImageFont.load_default()
    bounds = draw.textbbox((0, 0), attribution, font=font)
    text_width, text_height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    if width >= text_width + 8:
        x, y = width - text_width - 5, height - text_height - 5
        draw.rectangle((x - 3, y - 3, width, height), fill="#ffffff")
        draw.text((x, y), attribution, fill="black", font=font)

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@router.get("/v1/static-map")
def static_map(
    pins: str,
    width: int = Query(..., ge=64, le=1280),
    height: int = Query(..., ge=64, le=1280),
    user=Depends(current_user),
):
    points = parse_pins(pins)
    limit("static-map:" + user.id, 30, 60)
    limit("static-map:global", 60, 60)
    image = render_map(points, width, height)
    if image is None:
        record_fallback(
            purpose="static_map",
            from_profile="configured_osm_tiles",
            to_profile="app_pin_canvas",
            reason="tiles_unavailable",
            outcome="degraded",
        )
        raise HTTPException(502, "Map tiles are temporarily unavailable")
    return Response(content=image, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
