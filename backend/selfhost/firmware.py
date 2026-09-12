"""Firmware is provisioned by the operator; no GitHub lookup at runtime."""

import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from selfhost.config import settings
from selfhost.security import current_user

router = APIRouter()


def firmware_file(filename):
    root = settings().data_dir / "firmware"
    if Path(filename).name != filename or not filename.endswith((".zip", ".bin")):
        raise HTTPException(404, "Firmware not found")
    path = (root / filename).resolve()
    if path.parent != root.resolve() or not path.is_file():
        raise HTTPException(404, "Firmware not installed")
    return path


def release(request, model, channel):
    path = settings().data_dir / "firmware" / "manifest.json"
    if not path.is_file():
        return {}
    release = json.loads(path.read_text()).get(model, {}).get(channel)
    if not release:
        return {}
    file = firmware_file(release["filename"])
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    if digest != release["sha256"]:
        raise HTTPException(503, "Installed firmware checksum mismatch")
    return {k: v for k, v in release.items() if k not in {"filename", "sha256"}} | {
        "zip_url": str(request.base_url).rstrip("/") + "/v1/firmware/files/" + file.name
    }


@router.get("/v2/firmware/latest")
def latest(request: Request, device_model: str, user=Depends(current_user)):
    return release(request, device_model, "latest")


@router.get("/v2/firmware/stable")
def stable(request: Request, device_model: str, user=Depends(current_user)):
    return release(request, device_model, "stable")


@router.get("/v1/firmware/files/{filename}")
def download(filename: str):
    # Firmware contains no user data. The native OTA downloader uses a plain GET.
    path = firmware_file(filename)
    return FileResponse(path, filename=filename, media_type="application/octet-stream")
