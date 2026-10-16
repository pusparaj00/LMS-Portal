"""Create staff accounts (F-01). Self-registration only creates students.

Usage: NEW_USER_PASSWORD=... python -m app.manage create-user EMAIL instructor|admin
"""
import argparse
import getpass
import os

from sqlalchemy import text

from app import audit
from app.auth import hash_password
from app.db import get_engine


def create_user(email: str, role: str, password: str) -> int:
    with get_engine().begin() as conn:
        user_id = conn.execute(
            text(
                "INSERT INTO users (email, password_hash, role) VALUES (lower(:e), :h, :r)"
                " RETURNING id"
            ),
            {"e": email, "h": hash_password(password), "r": role},
        ).scalar_one()
        audit.record("staff.created", user_id=user_id, detail={"role": role, "via": "app.manage"}, conn=conn)
        return user_id


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-user")
    create.add_argument("email")
    create.add_argument("role", choices=["instructor", "admin"])
    args = parser.parse_args()
    password = os.environ.get("NEW_USER_PASSWORD") or getpass.getpass("Password: ")
    print(f"created user {create_user(args.email, args.role, password)}")


if __name__ == "__main__":
    main()
