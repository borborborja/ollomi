"""Local account bootstrap shared by startup and administrative commands."""

import logging
import os

from sqlalchemy import select, update

from selfhost.db import McpApiKey, McpOauthToken, Session, User
from selfhost.security import passwords, verify_password

logger = logging.getLogger(__name__)


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not email or "@" not in email:
        raise ValueError("A valid administrator email is required")
    return email


def validate_password(value: str) -> str:
    if len(value) < 12:
        raise ValueError("Passwords must contain at least 12 characters")
    return value


def create_admin(db, email: str, password: str, *, if_missing: bool = False) -> bool:
    """Create one administrator, returning False only for an idempotent seed."""
    email = normalize_email(email)
    password = validate_password(password)
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        if if_missing:
            return False
        raise ValueError("Account already exists")
    db.add(
        User(
            email=email,
            name=email.split("@", 1)[0],
            password_hash=passwords.hash(password),
            admin=True,
        )
    )
    return True


def seed_admin_from_env(db) -> bool:
    """Keep the environment-owned administrator in sync on every startup."""
    email = os.getenv("OLLOMI_ADMIN_EMAIL", "").strip()
    password = os.getenv("OLLOMI_ADMIN_PASSWORD", "")
    if not email and not password:
        return False
    if not email or not password:
        raise ValueError("OLLOMI_ADMIN_EMAIL and OLLOMI_ADMIN_PASSWORD must be set together")
    email = normalize_email(email)
    validate_password(password)
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        if not existing.admin:
            raise ValueError("OLLOMI_ADMIN_EMAIL belongs to a non-administrator account")
        changed = not verify_password(password, existing.password_hash)
        existing.enabled = True
        if changed:
            existing.password_hash = passwords.hash(password)
            db.execute(update(Session).where(Session.user_id == existing.id).values(revoked=True))
            db.execute(update(McpOauthToken).where(McpOauthToken.user_id == existing.id).values(revoked=True))
            db.execute(update(McpApiKey).where(McpApiKey.user_id == existing.id).values(revoked=True))
            logger.info("Updated environment-owned Ollomi administrator credentials")
        return changed
    create_admin(db, email, password)
    logger.info("Created initial Ollomi administrator")
    return True
