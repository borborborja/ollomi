import argparse
import getpass
import os
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import select, update
from pathlib import Path

from selfhost.accounts import create_admin, normalize_email, validate_password
from selfhost.db import Session, User, transaction
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


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ollomi")
    parser.add_argument("command", choices=["migrate", "create-admin", "reset-password"])
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
