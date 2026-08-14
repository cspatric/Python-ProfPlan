"""Request/response schemas for the auth endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field

from app.modules.users.domain.entities import UserRole, UserStatus
from app.shared.validation import RequiredText


class ProvidersResponse(BaseModel):
    """Which external sign-in providers this deployment can actually use.

    The frontend asks rather than being told at build time: whether Google is
    configured is a property of the running backend, and a button that posts to
    an endpoint that is not registered is the failure this avoids.
    """

    google: bool


class LoginRequest(BaseModel):
    """Credentials submitted to the login endpoint."""

    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    """Payload to create a new account."""

    name: RequiredText = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    """Ask for a reset link. Answered identically whether or not it exists."""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Spend a reset token and set a new password."""

    token: str = Field(min_length=16, max_length=512)
    password: str = Field(min_length=8, max_length=128)


class SetPasswordRequest(BaseModel):
    """Set a password from inside the session.

    `current_password` is required only when the account already has one. An
    account created by signing in with Google has none, and asking for a
    password it never had would make the first one impossible to set.
    """

    current_password: str | None = None
    password: str = Field(min_length=8, max_length=128)


class PasswordSetResponse(BaseModel):
    """The answer to setting a password.

    `sessions_ended` rather than a sentence the client has to read: changing a
    password ends every session and setting the first one does not, and the app
    has to know which happened to decide whether to send the person back to the
    sign-in page.
    """

    detail: str
    sessions_ended: bool


class EmailVerificationConfirm(BaseModel):
    """Spend a verification token."""

    token: str = Field(min_length=16, max_length=512)


class UserResponse(BaseModel):
    """Public representation of a user."""

    model_config = ConfigDict(from_attributes=True)

    uuid: uuid.UUID
    name: str
    email: EmailStr
    profile_picture: str | None
    status: UserStatus
    role: UserRole
    last_login_at: datetime | None
    email_verified_at: datetime | None

    # Exposed so the app can offer to set one, which is the whole point of the
    # flag: an account that arrived through Google has no password and cannot
    # sign in any other way until it does. The hash itself never leaves here.
    password_hash: str | None = Field(default=None, exclude=True, repr=False)

    @computed_field
    @property
    def has_password(self) -> bool:
        return self.password_hash is not None


class MessageResponse(BaseModel):
    """Generic message payload."""

    detail: str
