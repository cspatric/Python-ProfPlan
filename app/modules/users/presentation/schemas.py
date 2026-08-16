"""Request/response schemas for the account data endpoints."""

from pydantic import BaseModel


class AccountErasureRequest(BaseModel):
    """Confirming a deletion that cannot be undone.

    One of the two is required, and which one depends on the account. A
    password is the proof for an account that has one; an account that only
    signs in with Google has no password to give, so it confirms by typing its
    own address, which is the same thing a bank asks for and for the same
    reason: it makes the action deliberate.
    """

    password: str | None = None
    confirm_email: str | None = None


class AccountErasedResponse(BaseModel):
    """What the deletion actually removed."""

    detail: str
    documents_removed: int
    subjects: int
