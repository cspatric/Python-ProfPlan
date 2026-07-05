"""Create a user from the command line.

Usage (inside the api container):
    python scripts/create_user.py <email> <name> <password> [role]

`role` is "user" (default) or "admin".
"""

import asyncio
import sys

from app.core.security import hash_password
from app.infrastructure.database.session import SessionFactory
from app.modules.users.domain.entities import UserRole
from app.modules.users.infrastructure.repository import UserRepository


async def _main(email: str, name: str, password: str, role: UserRole) -> None:
    async with SessionFactory() as session:
        repo = UserRepository(session)
        if await repo.get_by_email(email):
            print(f"User already exists: {email}")
            return
        user = await repo.create(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
        )
        await session.commit()
        print(f"Created {user.role.value} {user.email} ({user.uuid})")


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        print(
            "Usage: python scripts/create_user.py "
            "<email> <name> <password> [user|admin]"
        )
        raise SystemExit(1)
    user_role = UserRole(sys.argv[4]) if len(sys.argv) == 5 else UserRole.USER
    asyncio.run(_main(sys.argv[1], sys.argv[2], sys.argv[3], user_role))
