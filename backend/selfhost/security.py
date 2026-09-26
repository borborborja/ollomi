import base64
import hashlib
import secrets
from datetime import timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update

from selfhost.config import settings
from selfhost.db import McpApiKey, McpOauthToken, Session, User, now, transaction

passwords = PasswordHasher()
bearer = HTTPBearer(auto_error=False)


def cipher():
    return Fernet(
        base64.urlsafe_b64encode(
            hashlib.sha256(settings().secret_key.get_secret_value().encode()).digest()
        )
    )


def seal(value):
    return cipher().encrypt(value.encode()).decode() if value else ""


def unseal(value):
    return cipher().decrypt(value.encode()).decode() if value else ""


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def user_wire(user):
    return {
        "id": user.id,
        "uid": user.id,
        "email": user.email,
        "display_name": user.name,
        "admin": user.admin,
    }


def tokens(db, user, session=None):
    refresh = secrets.token_urlsafe(48)
    if session is None:
        session = Session(user_id=user.id)
        db.add(session)
    session.refresh_hash = digest(refresh)
    session.expires_at = now() + timedelta(days=settings().refresh_days)
    db.flush()
    expires = now() + timedelta(minutes=settings().access_minutes)
    access = jwt.encode(
        {
            "sub": user.id,
            "sid": session.id,
            "exp": expires,
            "iat": now(),
            "iss": "ollomi",
            "aud": "ollomi-app",
        },
        settings().secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_at": expires.isoformat(),
        "user": user_wire(user),
    }


def authenticate(token):
    try:
        claims = jwt.decode(
            token,
            settings().secret_key.get_secret_value(),
            algorithms=["HS256"],
            audience="ollomi-app",
            issuer="ollomi",
        )
        with transaction() as db:
            session = db.get(Session, claims["sid"])
            user = db.get(User, claims["sub"])
            if (
                not session
                or session.revoked
                or session.user_id != claims["sub"]
                or aware(session.expires_at) <= now()
                or not user
                or not user.enabled
            ):
                raise ValueError("Invalid session")
            return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(
            401, "Session expired", headers={"WWW-Authenticate": "Bearer"}
        ) from None


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None:
        raise HTTPException(
            401, "Authentication required", headers={"WWW-Authenticate": "Bearer"}
        )
    return authenticate(credentials.credentials)


def administrator(user: User = Depends(current_user)):
    if not user.admin:
        raise HTTPException(403, "Administrator required")
    return user


def verify_password(value, encoded):
    try:
        return passwords.verify(encoded, value)
    except VerificationError:
        return False


def revoke_credentials(db, user_id, *, keep_session_id=None):
    """Revoke all sessions and MCP credentials for a user.

    When keep_session_id is given, that single Session row is left untouched.
    """
    session_query = update(Session).where(Session.user_id == user_id).values(revoked=True)
    if keep_session_id is not None:
        session_query = session_query.where(Session.id != keep_session_id)
    db.execute(session_query)
    db.execute(update(McpOauthToken).where(McpOauthToken.user_id == user_id).values(revoked=True))
    db.execute(update(McpApiKey).where(McpApiKey.user_id == user_id).values(revoked=True))


def rotate(refresh):
    with transaction() as db:
        session = db.scalar(
            select(Session)
            .where(Session.refresh_hash == digest(refresh))
            .with_for_update()
        )
        if not session or session.revoked or aware(session.expires_at) <= now():
            raise HTTPException(401, "Session expired")
        user = db.get(User, session.user_id)
        if not user or not user.enabled:
            raise HTTPException(401, "Session expired")
        return tokens(db, user, session)
