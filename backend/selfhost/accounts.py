"""Local account bootstrap shared by startup and administrative commands."""

import logging
import os

from sqlalchemy import select

from selfhost.db import User
from selfhost.security import passwords

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
    """Create the initial admin once when both bootstrap variables are present."""
    email = os.getenv("OLLOMI_ADMIN_EMAIL", "").strip()
    password = os.getenv("OLLOMI_ADMIN_PASSWORD", "")
    if not email and not password:
        return False
    if not email or not password:
        raise ValueError("OLLOMI_ADMIN_EMAIL and OLLOMI_ADMIN_PASSWORD must be set together")
    created = create_admin(db, email, password, if_missing=True)
    if created:
        logger.info("Created initial Ollomi administrator")
    return created
