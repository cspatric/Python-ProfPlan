"""Request/response schemas for the auth endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.users.domain.entities import UserRole, UserStatus


class LoginRequest(BaseModel):
    """Credentials submitted to the login endpoint."""

    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    """Payload to create a new account."""

    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


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


class MessageResponse(BaseModel):
    """Generic message payload."""

    detail: str
