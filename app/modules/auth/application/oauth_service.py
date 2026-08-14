"""Turning a Google identity into a session here.

Three cases, and the third is the one with the sharp edge.

1. **The Google account is already linked.** Sign that user in.
2. **Nobody has this Google account, and no local account has the address.**
   Create one, with no password, linked to the provider.
3. **Nobody has this Google account, but a local account has the address.**
   This is the account takeover shape: anyone who can make an identity provider
   assert an address could otherwise walk into an existing account. It is
   allowed here **only when Google says the address is verified**, which is
   Google asserting it controls that mailbox, and refused otherwise.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.domain.exceptions import EmailNotVerifiedError
from app.modules.auth.infrastructure.google_oauth import GoogleIdentity
from app.modules.auth.infrastructure.models import AuthEvent, Provider, UserProvider
from app.modules.users.domain.entities import UserStatus
from app.modules.users.infrastructure.models import User

logger = logging.getLogger("app.oauth")

GOOGLE_SLUG = "google"


class OAuthService:
    """Finds or creates the local account behind an external identity."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _provider_id(self, slug: str, name: str) -> UUID:
        """The provider row, created on first use.

        Seeding it in a migration would be one more thing to keep in step with
        the code; creating it the first time somebody signs in cannot drift.
        """
        found = await self._session.scalar(
            select(Provider).where(Provider.slug == slug)
        )
        if found is not None:
            return found.uuid

        provider = Provider(slug=slug, name=name)
        self._session.add(provider)
        await self._session.flush()
        return provider.uuid

    async def sign_in_with_google(self, identity: GoogleIdentity) -> User:
        """Return the user this Google identity belongs to, creating if needed."""
        provider_id = await self._provider_id(GOOGLE_SLUG, "Google")

        # 1. Already linked. The provider's subject is the key, not the email:
        #    an address can change hands, `sub` cannot.
        linked = await self._session.scalar(
            select(User)
            .join(UserProvider, UserProvider.user_id == User.uuid)
            .where(
                UserProvider.provider_id == provider_id,
                UserProvider.provider_user_id == identity.subject,
                User.deleted_at.is_(None),
            )
        )
        if linked is not None:
            return linked

        existing = await self._session.scalar(
            select(User).where(User.email == identity.email, User.deleted_at.is_(None))
        )

        # 3. An account already owns this address.
        if existing is not None:
            if not identity.email_verified:
                # Refusing here is the whole point: without it, anyone who can
                # get a provider to assert an address walks into the account.
                logger.warning(
                    "refused to link an unverified Google address to an account",
                    extra={"email": identity.email},
                )
                raise EmailNotVerifiedError
            self._link(existing.uuid, provider_id, identity.subject)
            return existing

        # 2. Nobody at all: a new account, with no password.
        user = User(
            name=identity.name,
            email=identity.email,
            password_hash=None,
            status=UserStatus.ACTIVE,
        )
        # Google already proved the mailbox, so asking the person to prove it
        # again by clicking a link in it would be theatre.
        if identity.email_verified:
            from datetime import UTC, datetime

            user.email_verified_at = datetime.now(UTC)

        self._session.add(user)
        await self._session.flush()
        self._link(user.uuid, provider_id, identity.subject)
        return user

    def _link(self, user_id: UUID, provider_id: UUID, subject: str) -> None:
        self._session.add(
            UserProvider(
                user_id=user_id, provider_id=provider_id, provider_user_id=subject
            )
        )


#: Re-exported so the router can log the event without importing the model.
LOGIN_EVENT = AuthEvent.LOGIN_SUCCESS
