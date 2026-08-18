"""The two things an account must always be able to do: leave, and take its
data with it."""

import json
import logging

from fastapi import APIRouter, Request, Response

from app.api.rate_limit import auth_limit
from app.core.security import verify_password
from app.modules.auth.presentation.dependencies import CurrentUser
from app.modules.users.presentation.dependencies import AccountDataServiceDep
from app.modules.users.presentation.schemas import (
    AccountErasedResponse,
    AccountErasureRequest,
)
from app.shared.exceptions.base import UnauthorizedError

logger = logging.getLogger("app.users")
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/export")
@auth_limit
async def export_my_data(
    request: Request,
    response: Response,
    user: CurrentUser,
    service: AccountDataServiceDep,
) -> Response:
    """Everything this account owns, as a JSON file.

    A download rather than a JSON body: this is a person exercising a right,
    not a client calling an API, and what they need at the end of it is a file
    on their disk.
    """
    payload = await service.export(user)
    logger.info("account exported", extra={"user_id": str(user.uuid)})
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": (f'attachment; filename="profplan-{user.uuid}.json"')
        },
    )


@router.post("/me/delete", response_model=AccountErasedResponse)
@auth_limit
async def erase_my_account(
    payload: AccountErasureRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
    service: AccountDataServiceDep,
) -> AccountErasedResponse:
    """Delete this account and everything it owns. There is no undo.

    POST rather than DELETE on purpose: this one carries a body, the
    confirmation, and a DELETE with a body is the kind of thing proxies and
    clients disagree about.
    """
    if user.password_hash is not None:
        if not payload.password or not verify_password(
            payload.password, user.password_hash
        ):
            raise UnauthorizedError("The password does not match")
    elif (payload.confirm_email or "").strip().lower() != user.email.lower():
        # No password to prove: the address, typed out, is what makes it
        # deliberate.
        raise UnauthorizedError("Type the account's email address to confirm")

    removed = await service.erase(user)
    # The cookies point at an account that no longer exists.
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    response.delete_cookie(key="csrf_token", path="/")
    return AccountErasedResponse(
        detail=(
            "Account deleted. Nothing of it is kept but the security log, "
            "without your name in it."
        ),
        **removed,
    )
