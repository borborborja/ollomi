from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update

from selfhost.db import AIProfile, Job, Session, User, emit, transaction
from selfhost.profiles import (
    completion,
    embed,
    env_managed,
    mark_profile_health,
    provider_client,
    public_profile,
    selected_profile,
    snapshot,
    validate_url,
)
from selfhost.security import (
    administrator,
    current_user,
    digest,
    passwords,
    rotate,
    seal,
    tokens,
    user_wire,
    verify_password,
)

router = APIRouter()


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class Refresh(Input):
    refresh_token: str = Field(min_length=1, max_length=200)


class UserInput(Login):
    password: str = Field(min_length=12, max_length=1024)
    name: str = Field(default="", max_length=200)
    admin: bool = False


class UserUpdate(Input):
    enabled: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=1024)


class ChatOptions(Input):
    max_tokens: int = Field(default=2048, ge=32, le=8192)
    temperature: float = Field(default=0.2, ge=0, le=2)
    prompt_suffix: str = Field(default="", max_length=200)
    reasoning_effort: Literal["none", "low", "medium", "high"] | None = None


class ProfileInput(Input):
    name: str = Field(min_length=1, max_length=100)
    purpose: Literal["chat", "embedding", "stt"]
    base_url: str = Field(max_length=2000)
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=4096)
    external: bool = False
    enabled: bool = True
    options: ChatOptions | None = None


@router.post("/v1/auth/login")
def login(body: Login, request: Request):
    from selfhost.rate_limit import limit

    limit("login:" + (request.client.host if request.client else "unknown"), 10, 60)
    with transaction() as db:
        user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
        # Equal-cost verification avoids revealing whether an account exists.
        encoded = user.password_hash if user else _DUMMY_HASH
        valid = verify_password(body.password, encoded)
        if not user or not valid or not user.enabled:
            raise HTTPException(401, "Invalid email or password")
        return tokens(db, user)


_DUMMY_HASH = passwords.hash("not-a-real-password")


@router.post("/v1/auth/refresh")
def refresh(body: Refresh):
    return rotate(body.refresh_token)


@router.post("/v1/auth/logout")
def logout(body: Refresh):
    with transaction() as db:
        db.execute(
            update(Session)
            .where(Session.refresh_hash == digest(body.refresh_token))
            .values(revoked=True)
        )
    return {"status": "ok"}


@router.get("/v1/auth/me")
def me(user=Depends(current_user)):
    with transaction() as db:
        effective = {}
        for purpose in ("chat", "stt", "embedding"):
            try:
                effective[purpose] = selected_profile(db, user.id, purpose)["id"]
            except HTTPException:
                pass
    return {
        **user_wire(user),
        "preferences": {**user.preferences, "ai_profiles": effective},
    }


@router.get("/v1/admin/users")
def users(admin=Depends(administrator)):
    with transaction() as db:
        return [
            {**user_wire(row), "enabled": row.enabled}
            for row in db.scalars(select(User).order_by(User.created_at))
        ]


@router.post("/v1/admin/users", status_code=201)
def create_user(body: UserInput, admin=Depends(administrator)):
    from sqlalchemy.exc import IntegrityError

    try:
        with transaction() as db:
            row = User(
                email=body.email.strip().lower(),
                name=body.name,
                password_hash=passwords.hash(body.password),
                admin=body.admin,
            )
            db.add(row)
            db.flush()
            return user_wire(row)
    except IntegrityError:
        raise HTTPException(409, "Email already registered") from None


@router.patch("/v1/admin/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, admin=Depends(administrator)):
    with transaction() as db:
        row = db.get(User, user_id)
        if not row:
            raise HTTPException(404, "User not found")
        if user_id == admin.id and body.enabled is False:
            raise HTTPException(409, "Cannot disable your own administrator account")
        if body.enabled is not None:
            row.enabled = body.enabled
        if body.password:
            row.password_hash = passwords.hash(body.password)
        if body.password or body.enabled is False:
            db.execute(
                update(Session).where(Session.user_id == user_id).values(revoked=True)
            )
        return user_wire(row)


@router.get("/v1/admin/ai-profiles")
def admin_profiles(admin=Depends(administrator)):
    with transaction() as db:
        return [
            public_profile(p, True)
            for p in db.scalars(select(AIProfile).order_by(AIProfile.name))
        ]


@router.get("/v1/ai-status")
def ai_status(user=Depends(current_user)):
    with transaction() as db:
        result = {}
        for purpose in ("stt", "chat", "embedding"):
            rows = list(
                db.scalars(
                    select(AIProfile).where(
                        AIProfile.purpose == purpose,
                        AIProfile.enabled.is_(True),
                    )
                )
            )
            managed = [
                row
                for row in rows
                if (row.capabilities or {}).get("managed_by") == "env"
            ]
            visible = sorted(
                managed or rows,
                key=lambda row: (row.capabilities or {}).get("priority", 999999),
            )
            profiles = [public_profile(row) for row in visible]
            successful = [
                profile
                for profile in profiles
                if profile["status"] == "healthy" and profile["last_success_at"]
            ]
            active = (
                max(successful, key=lambda profile: profile["last_success_at"])["id"]
                if successful
                else (
                    profiles[0]["id"]
                    if profiles
                    and all(profile["status"] == "unknown" for profile in profiles)
                    else None
                )
            )
            result[purpose] = {
                "managed_by_env": bool(managed),
                "active_profile_id": active,
                "profiles": profiles,
            }
        return result


@router.get("/v1/ai-profiles")
def profiles(user=Depends(current_user)):
    with transaction() as db:
        return [
            public_profile(p)
            for p in db.scalars(
                select(AIProfile)
                .where(AIProfile.enabled.is_(True))
                .order_by(AIProfile.name)
            )
        ]


def save_profile(body, profile_id=None):
    url = validate_url(body.base_url, body.external)
    with transaction() as db:
        if env_managed(db, body.purpose):
            raise HTTPException(
                409, f"{body.purpose} profiles are managed by environment"
            )
        row = db.get(AIProfile, profile_id) if profile_id else AIProfile()
        if row is None:
            raise HTTPException(404, "Profile not found")
        if (row.capabilities or {}).get("managed_by") == "env":
            raise HTTPException(409, "Environment-managed profiles are read-only")
        old = snapshot(row) if profile_id else None
        if old and old["purpose"] != body.purpose:
            raise HTTPException(422, "Create a new profile to change its purpose")
        for key, value in body.model_dump(
            exclude={"api_key", "base_url", "options"}
        ).items():
            setattr(row, key, value)
        row.base_url = url
        if body.options is not None:
            row.capabilities = {
                **(row.capabilities or {}),
                "options": body.options.model_dump(exclude_none=True),
            }
        if body.api_key is not None:
            row.encrypted_key = seal(body.api_key)
        if profile_id:
            row.revision += 1
        db.add(row)
        db.flush()
        if old and old["purpose"] == "embedding" and row.enabled:
            for user in db.scalars(select(User).where(User.enabled.is_(True))):
                try:
                    selected = selected_profile(db, user.id, "embedding")["id"]
                except HTTPException:
                    continue
                if selected == row.id:
                    db.add(
                        Job(
                            user_id=user.id,
                            kind="reindex",
                            payload={"embedding": snapshot(row)},
                        )
                    )
        return public_profile(row, True)


@router.post("/v1/admin/ai-profiles", status_code=201)
def add_profile(body: ProfileInput, admin=Depends(administrator)):
    return save_profile(body)


@router.put("/v1/admin/ai-profiles/{profile_id}")
def update_profile(profile_id: str, body: ProfileInput, admin=Depends(administrator)):
    return save_profile(body, profile_id)


@router.post("/v1/admin/ai-profiles/{profile_id}/validate")
def check_profile(profile_id: str, admin=Depends(administrator)):
    with transaction() as db:
        row = db.get(AIProfile, profile_id)
        if not row:
            raise HTTPException(404, "Profile not found")
        profile = snapshot(row)
    try:
        capabilities = {}
        if profile["purpose"] == "chat":
            completion(
                profile,
                [{"role": "user", "content": "Reply with OK."}],
                fallback=False,
            )
            capabilities["chat"] = True
        elif profile["purpose"] == "embedding":
            capabilities["dimensions"] = len(
                embed(profile, ["Connection test"], fallback=False)[0]
            )
        else:
            import io
            import wave

            audio = io.BytesIO()
            with wave.open(audio, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 16000)
            with provider_client(profile) as client:
                response = client.post(
                    "audio/transcriptions",
                    files={"file": ("silence.wav", audio.getvalue(), "audio/wav")},
                    data={"model": profile["model"]},
                )
                response.raise_for_status()
                if "text" not in response.json():
                    raise ValueError("No transcription text")
            capabilities["transcription"] = True
        mark_profile_health(profile, True)
    except Exception:
        mark_profile_health(profile, False)
        raise HTTPException(
            502,
            "Provider validation failed; check URL, credentials, model and supported operation",
        ) from None
    with transaction() as db:
        row = db.get(AIProfile, profile_id)
        if row.revision != profile["revision"]:
            raise HTTPException(409, "Profile changed during validation")
        row.capabilities = {**row.capabilities, **capabilities}
    return {"ok": True, "capabilities": capabilities}


@router.put("/v1/users/me/ai-profiles")
def select_profiles(body: dict[str, str], user=Depends(current_user)):
    if set(body) - {"chat", "embedding", "stt"}:
        raise HTTPException(422, "Unknown AI purpose")
    with transaction() as db:
        row = db.get(User, user.id)
        previous = (row.preferences or {}).get("ai_profiles", {})
        for purpose, profile_id in body.items():
            if env_managed(db, purpose):
                raise HTTPException(
                    409, f"{purpose} profiles are managed by environment"
                )
            profile = db.get(AIProfile, profile_id)
            if not profile or not profile.enabled or profile.purpose != purpose:
                raise HTTPException(422, "Profile is not available for this purpose")
        row.preferences = {**row.preferences, "ai_profiles": {**previous, **body}}
        if "embedding" in body and previous.get("embedding") != body["embedding"]:
            db.add(
                Job(
                    user_id=user.id,
                    kind="reindex",
                    payload={"embedding": selected_profile(db, user.id, "embedding")},
                )
            )
        emit(db, user.id, "settings_updated", {})
        return row.preferences["ai_profiles"]


@router.post("/v1/users/me/reindex", status_code=202)
def reindex(user=Depends(current_user)):
    with transaction() as db:
        job = Job(
            user_id=user.id,
            kind="reindex",
            payload={"embedding": selected_profile(db, user.id, "embedding")},
        )
        db.add(job)
        db.flush()
        return {"job_id": job.id, "status": "queued"}
