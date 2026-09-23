"""Administrator settings with explicit environment precedence."""

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from selfhost.config import (
    INFRASTRUCTURE_FIELDS,
    RESTART_FIELDS,
    Settings,
    encode_override,
    environment_locked,
    environment_settings,
    settings,
)
from selfhost.db import Instance, transaction
from selfhost.security import administrator

router = APIRouter()
SECRET_FIELDS = {"secret_key", "typesense_key", "voiceprint_api_key"}
COMPOSE_FIELDS = (
    "COMPOSE_FILE", "OLLOMI_ENV_FILE", "OLLOMI_HOST_UID", "OLLOMI_HOST_GID",
    "OLLOMI_BIND", "OLLOMI_PORT", "OLLOMI_HTTPS_PORT", "OLLOMI_HTTP_PORT",
    "OLLOMI_TLS_BIND", "OLLOMI_TLS_DOMAIN", "OLLOMI_IMAGE_OWNER",
    "OLLOMI_IMAGE_TAG", "POSTGRES_PASSWORD", "TYPESENSE_API_KEY",
    "WHISPER_MODEL", "DIARIZATION",
)


class SettingValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any


def _editable(key: str):
    if key not in Settings.model_fields:
        raise HTTPException(404, "Unknown setting")
    if key in INFRASTRUCTURE_FIELDS:
        raise HTTPException(409, "Infrastructure settings require Compose")
    if environment_locked(key):
        raise HTTPException(409, "This setting is controlled by the environment")


@router.get("/v1/admin/config")
def get_config(admin=Depends(administrator)):
    effective = settings()
    with transaction() as db:
        stored = {
            row.key.removeprefix("setting:")
            for row in db.query(Instance).filter(Instance.key.like("setting:%"))
        }
    result = []
    for key, field in Settings.model_fields.items():
        secret = key in SECRET_FIELDS
        value = getattr(effective, key)
        result.append({
            "key": key,
            "env": "OLLOMI_" + key.upper(),
            "value": None if secret else str(value) if not isinstance(value, (str, int, float, bool)) else value,
            "has_value": bool(value.get_secret_value()) if secret else value is not None,
            "type": "secret" if secret else "boolean" if field.annotation is bool else "number" if field.annotation in (int, float) else "text",
            "source": "environment" if environment_locked(key) else "panel" if key in stored else "default",
            "editable": key not in INFRASTRUCTURE_FIELDS and not environment_locked(key),
            "restart_required": key in RESTART_FIELDS or key in INFRASTRUCTURE_FIELDS,
        })
    for key in COMPOSE_FIELDS:
        result.append({
            "key": key, "env": key, "value": None if "PASSWORD" in key or "API_KEY" in key else os.getenv(key),
            "has_value": bool(os.getenv(key)), "type": "secret" if "PASSWORD" in key or "API_KEY" in key else "text",
            "source": "environment" if key in os.environ else "unset",
            "editable": False, "restart_required": True,
        })
    return result


@router.put("/v1/admin/config/{key}")
def put_config(key: str, body: SettingValue, admin=Depends(administrator)):
    _editable(key)
    try:
        value = TypeAdapter(Settings.model_fields[key].annotation).validate_python(body.value)
        candidate = settings().model_copy(update={key: value})
        candidate.validate_runtime()
    except (ValidationError, ValueError) as error:
        raise HTTPException(422, "Invalid setting value or incompatible configuration") from error
    serializable = value.get_secret_value() if hasattr(value, "get_secret_value") else value
    if hasattr(serializable, "as_posix"):
        serializable = serializable.as_posix()
    with transaction() as db:
        row = db.get(Instance, "setting:" + key)
        if row is None:
            row = Instance(key="setting:" + key)
            db.add(row)
        row.value = encode_override(environment_settings(), serializable)
    settings.cache_clear()
    return {"status": "saved", "restart_required": key in RESTART_FIELDS}


@router.delete("/v1/admin/config/{key}")
def delete_config(key: str, admin=Depends(administrator)):
    _editable(key)
    with transaction() as db:
        row = db.get(Instance, "setting:" + key)
        if row is not None:
            db.delete(row)
    settings.cache_clear()
    return {"status": "default_restored"}
