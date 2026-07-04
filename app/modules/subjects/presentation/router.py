"""Subject HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.modules.auth.presentation.dependencies import CurrentUser
from app.modules.subjects.domain.exceptions import SubjectNotFoundError
from app.modules.subjects.presentation.dependencies import SubjectServiceDep
from app.modules.subjects.presentation.schemas import (
    SubjectCreate,
    SubjectResponse,
    SubjectUpdate,
)

router = APIRouter(prefix="/subjects", tags=["subjects"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found"
)


@router.post("", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
async def create_subject(
    payload: SubjectCreate, user: CurrentUser, service: SubjectServiceDep
) -> SubjectResponse:
    """Create a subject owned by the authenticated user."""
    subject = await service.create(user_id=user.uuid, data=payload.model_dump())
    return SubjectResponse.model_validate(subject)


@router.get("", response_model=list[SubjectResponse])
async def list_subjects(
    user: CurrentUser,
    service: SubjectServiceDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[SubjectResponse]:
    """List the authenticated user's subjects."""
    subjects = await service.list(user_id=user.uuid, limit=limit, offset=offset)
    return [SubjectResponse.model_validate(s) for s in subjects]


@router.get("/{subject_id}", response_model=SubjectResponse)
async def get_subject(
    subject_id: UUID, user: CurrentUser, service: SubjectServiceDep
) -> SubjectResponse:
    """Return a single subject."""
    try:
        subject = await service.get(user_id=user.uuid, subject_id=subject_id)
    except SubjectNotFoundError as exc:
        raise _NOT_FOUND from exc
    return SubjectResponse.model_validate(subject)


@router.patch("/{subject_id}", response_model=SubjectResponse)
async def update_subject(
    subject_id: UUID,
    payload: SubjectUpdate,
    user: CurrentUser,
    service: SubjectServiceDep,
) -> SubjectResponse:
    """Update a subject."""
    try:
        subject = await service.update(
            user_id=user.uuid,
            subject_id=subject_id,
            data=payload.model_dump(exclude_unset=True),
        )
    except SubjectNotFoundError as exc:
        raise _NOT_FOUND from exc
    return SubjectResponse.model_validate(subject)


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(
    subject_id: UUID, user: CurrentUser, service: SubjectServiceDep
) -> None:
    """Delete a subject."""
    try:
        await service.delete(user_id=user.uuid, subject_id=subject_id)
    except SubjectNotFoundError as exc:
        raise _NOT_FOUND from exc
