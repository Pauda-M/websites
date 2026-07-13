"""Operational CLI for the API service.

Usage:
    python -m pb_api.cli create-admin --email admin@example.com \
        --full-name "Admin" [--password ...]

Admin/staff accounts are provisioned here (never via the public register
endpoint). If ``--password`` is omitted a strong one is generated and printed
once to stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys

from pb_api.core.config import get_settings
from pb_api.core.logging import configure_logging, get_logger
from pb_api.db.models.user import UserRole
from pb_api.db.session import create_engine, create_session_factory
from pb_api.services.users import EmailAlreadyRegisteredError, create_user

logger = get_logger(__name__)


async def _create_admin(email: str, full_name: str, password: str | None, role: UserRole) -> int:
    settings = get_settings()
    generated = password is None
    final_password = password or secrets.token_urlsafe(24)

    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            user = await create_user(
                session,
                email=email,
                password=final_password,
                full_name=full_name,
                role=role,
                password_min_length=settings.password_min_length,
            )
    except EmailAlreadyRegisteredError:
        print(f"error: {email} is already registered", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()

    logger.info("admin_user_created", email=user.email, role=user.role.value)
    print(f"created {user.role.value} user {user.email} (id={user.id})")
    if generated:
        print(f"generated password: {final_password}")
        print("store it now — it will not be shown again")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pb-api", description="PB Platform API admin CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-admin", help="Provision an admin or staff user")
    create.add_argument("--email", required=True)
    create.add_argument("--full-name", required=True)
    create.add_argument("--password", default=None, help="Omit to auto-generate")
    create.add_argument(
        "--role",
        default=UserRole.ADMIN.value,
        choices=[UserRole.ADMIN.value, UserRole.STAFF.value],
    )

    args = parser.parse_args(argv)
    configure_logging(get_settings())

    if args.command == "create-admin":
        return asyncio.run(
            _create_admin(args.email, args.full_name, args.password, UserRole(args.role))
        )
    parser.error(f"unknown command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
