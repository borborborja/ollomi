import argparse
import getpass

from alembic import command
from alembic.config import Config
from sqlalchemy import select, update
from pathlib import Path

from selfhost.db import Session, User, transaction
from selfhost.security import passwords


def main():
    parser = argparse.ArgumentParser(prog="ollomi")
    parser.add_argument(
        "command", choices=["migrate", "create-admin", "reset-password"]
    )
    parser.add_argument("--email")
    args = parser.parse_args()
    if args.command == "migrate":
        command.upgrade(Config(str(Path(__file__).with_name("alembic.ini"))), "head")
        return
    email = (args.email or input("Email: ")).strip().lower()
    password = getpass.getpass("Password (12+ characters): ")
    if len(password) < 12 or password != getpass.getpass("Repeat password: "):
        parser.error("Passwords must match and contain at least 12 characters")
    with transaction() as db:
        user = db.scalar(select(User).where(User.email == email))
        if args.command == "create-admin":
            if user:
                parser.error("Account already exists")
            db.add(
                User(
                    email=email,
                    name=email.split("@")[0],
                    password_hash=passwords.hash(password),
                    admin=True,
                )
            )
        else:
            if not user:
                parser.error("Account not found")
            user.password_hash = passwords.hash(password)
            db.execute(
                update(Session).where(Session.user_id == user.id).values(revoked=True)
            )
    print("Account updated")


if __name__ == "__main__":
    main()
