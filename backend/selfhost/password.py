"""Password management endpoints for the Ollomi selfhost fork.

Todos 6 and 7 of the password-change-recovery plan append `/v1/auth/password/reset`
and the authenticated `/v1/auth/password` change endpoint here; keep the shared
`router` and `Input` base at the top.
"""

import os
import secrets
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update

from selfhost import mail
from selfhost.accounts import normalize_email
from selfhost.config import settings
from selfhost.db import PasswordReset, User, now, transaction
from selfhost.security import digest

router = APIRouter()


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ForgotInput(Input):
    email: str = Field(min_length=3, max_length=254)


def _env_owned(user) -> bool:
    return bool(os.getenv("OLLOMI_ADMIN_PASSWORD")) and user.email == os.getenv("OLLOMI_ADMIN_EMAIL", "").strip().lower()


@router.post("/v1/auth/password/forgot")
def forgot(body: ForgotInput, request: Request, background: BackgroundTasks):
    from selfhost.rate_limit import limit

    limit("pwreset-ip:" + (request.client.host if request.client else "unknown"), 5, 900)
    email = normalize_email(body.email)
    limit("pwreset-email:" + digest(email), 3, 3600)
    if not mail.configured():
        raise HTTPException(503, "Email delivery is not configured")

    # Generate the token before the user lookup so the work does not depend on
    # whether the account exists (timing-safe anti-enumeration).
    token = secrets.token_urlsafe(32)
    token_digest = digest(token)

    link = None
    to = None
    language = ""
    with transaction() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user and user.enabled and not _env_owned(user):
            db.execute(
                delete(PasswordReset).where(
                    PasswordReset.user_id == user.id,
                    (PasswordReset.used_at.is_not(None)) | (PasswordReset.expires_at <= now()),
                )
            )
            db.execute(
                update(PasswordReset)
                .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
                .values(used_at=now())
            )
            db.add(
                PasswordReset(
                    user_id=user.id,
                    token_hash=token_digest,
                    expires_at=now() + timedelta(minutes=settings().password_reset_ttl_minutes),
                )
            )
            to = user.email
            language = (user.preferences or {}).get("language") or ""
            link = f"{settings().public_url.rstrip('/')}/reset-password#token={token}"

    if link is not None:
        # Capture only plain strings; never the request-scoped DB session.
        background.add_task(mail.send_password_reset_email, to, link, language)
    return {"status": "ok"}
