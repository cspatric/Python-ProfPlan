"""Create a user from the command line.

Usage (inside the api container):
    python scripts/create_user.py <email> <name> <password>
"""

import asyncio
import sys

from app.core.security import hash_password
from app.infrastructure.database.session import SessionFactory
from app.modules.users.infrastructure.repository import UserRepository


async def _main(email: str, name: str, password: str) -> None:
    async with SessionFactory() as session:
        repo = UserRepository(session)
        if await repo.get_by_email(email):
            print(f"User already exists: {email}")
            return
        user = await repo.create(
            name=name, email=email, password_hash=hash_password(password)
        )
        await session.commit()
        print(f"Created user {user.email} ({user.uuid})")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python scripts/create_user.py <email> <name> <password>")
        raise SystemExit(1)
    asyncio.run(_main(sys.argv[1], sys.argv[2], sys.argv[3]))
