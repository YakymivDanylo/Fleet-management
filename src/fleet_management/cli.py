"""Bootstrap the first administrator: `create-admin --email ... --full-name ...`.

Admins cannot self-register through the API, and POST /admin/admins needs an
existing admin, so the very first one is created from the server console.
"""

import argparse
import asyncio
import getpass
import os
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError

from .database import SessionLocal, engine
from .exceptions import EmailAlreadyRegisteredError
from .models import UserRole
from .services import user_service

MIN_PASSWORD_LENGTH = 8


async def _create_admin(email: str, password: str, full_name: str) -> None:
    try:
        async with SessionLocal() as db:
            user = await user_service.create_user(
                db, email, password, full_name, role=UserRole.ADMIN
            )
        print(f"Admin created: id={user.id} email={user.email}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an administrator account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", default="Administrator")
    args = parser.parse_args()

    # Same rule as POST /auth/register, so console-created accounts are not a backdoor
    # for addresses the API itself would reject.
    try:
        email = TypeAdapter(EmailStr).validate_python(args.email)
    except ValidationError:
        sys.exit(f"Invalid email address: {args.email}")

    # Read from the environment or an interactive prompt, never from argv:
    # command-line arguments end up in shell history and the process list.
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    try:
        asyncio.run(_create_admin(email, password, args.full_name))
    except EmailAlreadyRegisteredError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
