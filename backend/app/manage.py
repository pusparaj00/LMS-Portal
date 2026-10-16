"""Create staff accounts (F-01) and register LMS platforms for LTI launches (TR-A-09).

Self-registration only creates students.

Usage: NEW_USER_PASSWORD=... python -m app.manage create-user EMAIL instructor|admin
       python -m app.manage lti-add-platform --issuer I --client-id C --auth-url A --jwks-url J --deployment-id D
"""
import argparse
import getpass
import os

from sqlalchemy import text

from app import audit, lti, lti_grades
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
    platform = sub.add_parser("lti-add-platform", help="register an LMS for LTI 1.3 launches (TR-A-09)")
    platform.add_argument("--issuer", required=True, help="the platform's issuer, e.g. https://moodle.example.edu")
    platform.add_argument("--client-id", required=True, help="the client id the platform gave this tool")
    platform.add_argument("--auth-url", required=True, help="the platform's OIDC authentication request URL")
    platform.add_argument("--jwks-url", required=True, help="where the platform publishes its public keys")
    platform.add_argument("--deployment-id", required=True, action="append", help="repeat for several deployments")
    platform.add_argument("--token-url", help="the platform's OAuth2 token URL; needed to send grades")
    sub.add_parser("lti-tool-key", help="print a new LTI_TOOL_PRIVATE_KEY line for .env (keep it secret)")
    args = parser.parse_args()
    if args.command == "lti-add-platform":
        with get_engine().begin() as conn:
            platform_id = lti.register_platform(
                conn, issuer=args.issuer, client_id=args.client_id, auth_login_url=args.auth_url,
                jwks_url=args.jwks_url, deployment_ids=args.deployment_id, token_url=args.token_url,
            )
            audit.record(
                "lti.platform_registered", detail={"platform_id": platform_id, "issuer": args.issuer}, conn=conn
            )
        print(f"registered LTI platform {platform_id}")
        return
    if args.command == "lti-tool-key":
        print(f"LTI_TOOL_PRIVATE_KEY={lti_grades.new_tool_key()}")
        return
    password = os.environ.get("NEW_USER_PASSWORD") or getpass.getpass("Password: ")
    print(f"created user {create_user(args.email, args.role, password)}")


if __name__ == "__main__":
    main()
