import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from selfhost.config import settings
from selfhost.security import current_user

router = APIRouter()


class Speech(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    voice_id: str | None = None


@router.get("/v1/voices")
def voices(user=Depends(current_user)):
    try:
        with httpx.Client(timeout=20, trust_env=False) as client:
            result = client.get(settings().tts_url + "/v1/voices")
            result.raise_for_status()
            return result.json()
    except httpx.HTTPError:
        raise HTTPException(503, "Local speech synthesis service unavailable") from None


@router.post("/v2/tts/synthesize")
def synthesize(body: Speech, user=Depends(current_user)):
    voice = user.preferences.get("voice")
    try:
        with httpx.Client(timeout=120, trust_env=False) as client:
            result = client.post(
                settings().tts_url + "/v1/audio/speech",
                json={"input": body.text, "voice": voice},
            )
            result.raise_for_status()
            return Response(
                result.content,
                media_type="audio/mpeg",
                headers={"Cache-Control": "no-store"},
            )
    except httpx.HTTPError:
        raise HTTPException(
            503, "Install a Piper voice in the local model volume"
        ) from None
