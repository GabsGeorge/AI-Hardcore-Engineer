"""Seed a demonstration admin account from the ADMIN_SEED_EMAIL / ADMIN_SEED_PASSWORD env
vars. Prints the generated password **once** on stdout when ADMIN_SEED_PASSWORD is blank, so
the first run after `docker compose up` surfaces a credential the developer can log in with.

Guardrail: the script refuses to run with ``APP_ENV=production``. In production the first
admin is created by a one-off operations task, never from a seed with a shared default.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys

from app.auth import passwords, repo
from app.core.config import get_settings
from app.db.pool import close_pool, open_pool


async def _run(reset: bool) -> None:
    settings = get_settings()
    if settings.app_env == "production":
        print("refusing to seed an admin in production", file=sys.stderr)
        sys.exit(2)

    display_name = "Administração Getnet"
    email = settings.admin_seed_email
    if settings.password_pepper is None:
        print(
            "PASSWORD_PEPPER is not configured; cannot hash the demo password",
            file=sys.stderr,
        )
        sys.exit(2)

    password_secret = settings.admin_seed_password
    generated = False
    if password_secret is None:
        raw_password = secrets.token_urlsafe(16)
        generated = True
    else:
        raw_password = password_secret.get_secret_value()
    if len(raw_password) < passwords.MIN_LENGTH:
        print(
            f"ADMIN_SEED_PASSWORD must be at least {passwords.MIN_LENGTH} chars",
            file=sys.stderr,
        )
        sys.exit(2)

    pool = await open_pool(settings.database_url)
    try:
        existing = await repo.get_account_by_email(pool, email)
        if existing is None:
            account = await repo.create_account(
                pool,
                email=email,
                display_name=display_name,
                role="admin",
                status="active",
            )
        else:
            account = existing
            if not reset:
                print(f"admin account already exists: {account.id}", file=sys.stderr)
                sys.exit(0)
        await repo.set_password(pool, account.id, passwords.hash_password(raw_password))
        await repo.activate_account(pool, account.id)
    finally:
        await close_pool()

    print(f"email:    {email}")
    print("role:     admin")
    print(f"account:  {account.id}")
    if generated:
        print(f"password: {raw_password}")
        print("(sem ADMIN_SEED_PASSWORD; esta senha só é mostrada agora)")
    else:
        print("password: (lido do ADMIN_SEED_PASSWORD)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="replace the password of an existing demo admin",
    )
    args = parser.parse_args()
    asyncio.run(_run(reset=args.reset))


if __name__ == "__main__":
    main()
