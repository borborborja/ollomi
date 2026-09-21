import argparse
import getpass
import os
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import select, text, update
from pathlib import Path

from selfhost.accounts import create_admin, normalize_email, validate_password
from selfhost.db import Job, Session, User, transaction
from selfhost.profiles import selected_profile
from selfhost.search import purge_all_text_index
from selfhost.security import passwords


def _read_password(args, parser):
    if args.password_env:
        password = os.getenv(args.password_env)
        if password is None:
            parser.error(f"Environment variable {args.password_env} is not set")
        try:
            return validate_password(password)
        except ValueError as error:
            parser.error(str(error))
    if args.password_stdin:
        try:
            return validate_password(sys.stdin.readline().rstrip("\r\n"))
        except ValueError as error:
            parser.error(str(error))
    password = getpass.getpass("Password (12+ characters): ")
    if password != getpass.getpass("Repeat password: "):
        parser.error("Passwords must match")
    try:
        return validate_password(password)
    except ValueError as error:
        parser.error(str(error))


def rebuild_search_index():
    """Discard derived search data and queue a complete owner-scoped rebuild.

    Resolve profiles before deleting either index, so a bad restored provider
    configuration leaves the existing derived data untouched and fails loudly.
    """
    with transaction() as db:
        profiles = [
            (user.id, selected_profile(db, user.id, "embedding"))
            for user in db.scalars(select(User).where(User.enabled.is_(True)))
        ]
    purge_all_text_index()
    with transaction() as db:
        # Both stores are derived from records.  Clearing all vector generations
        # avoids retaining incompatible or stale vectors after a restore.
        db.execute(text("DELETE FROM embeddings"))
        for user_id, profile in profiles:
            db.add(Job(user_id=user_id, kind="reindex", payload={"embedding": profile}))
    return len(profiles)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ollomi")
    parser.add_argument(
        "command",
        choices=["migrate", "create-admin", "reset-password", "rebuild-search-index"],
    )
    parser.add_argument("--email")
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--password-env",
        metavar="VARIABLE",
        help="read the password from this environment variable",
    )
    source.add_argument(
        "--password-stdin",
        action="store_true",
        help="read one password line from standard input",
    )
    args = parser.parse_args(argv)
    if args.command == "migrate":
        command.upgrade(Config(str(Path(__file__).with_name("alembic.ini"))), "head")
        return
    if args.command == "rebuild-search-index":
        queued = rebuild_search_index()
        print(f"Search index cleared; queued rebuild for {queued} enabled user(s)")
        return
    try:
        email = normalize_email(args.email or input("Email: "))
    except ValueError as error:
        parser.error(str(error))
    password = _read_password(args, parser)
    with transaction() as db:
        user = db.scalar(select(User).where(User.email == email))
        if args.command == "create-admin":
            try:
                create_admin(db, email, password)
            except ValueError as error:
                parser.error(str(error))
        else:
            if not user:
                parser.error("Account not found")
            user.password_hash = passwords.hash(password)
            db.execute(update(Session).where(Session.user_id == user.id).values(revoked=True))
    print("Account updated")


if __name__ == "__main__":
    main()
