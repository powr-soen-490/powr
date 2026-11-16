# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Invite endpoints: owners create and revoke invite links; the invited person accepts one."""

import logging
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import OwnerDep
from app.core.database import get_db
from app.modules.invites import service
from app.schemas.invites import (
    AcceptInviteRequest,
    AcceptInviteResponse,
    CreateInviteRequest,
    CreateInviteResponse,
    RevokeInviteResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/invites", tags=["invites"])
DbSession = Annotated[Session, Depends(get_db)]

# Frontend route the owner shares; the accept-invite page itself is #115.
ACCEPT_PATH = "/accept-invite?token="

ACCOUNT_EXISTS_ERROR = "This email already has a powr account."
INVALID_INVITE_ERROR = "This invite link is invalid, expired or already used."
NOT_FOUND_ERROR = "Invite not found."
STORAGE_ERROR = "Could not process the invite. Try again."


def _storage_error(exc: service.InviteStorageError) -> HTTPException:
    logger.error("Database error while handling an invite", exc_info=exc)
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=STORAGE_ERROR)


@router.post("", response_model=CreateInviteResponse, status_code=status.HTTP_201_CREATED)
def create_invite(
    payload: CreateInviteRequest, user: OwnerDep, db: DbSession
) -> CreateInviteResponse:
    try:
        invite = service.create_invite(db, restaurant_id=user.restaurant_id, email=payload.email)
    except service.AccountAlreadyExistsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=ACCOUNT_EXISTS_ERROR) from exc
    except service.InviteStorageError as exc:
        raise _storage_error(exc) from exc

    logger.info(
        "Invite created (invite_id=%s, restaurant_id=%s)", invite.invite_id, user.restaurant_id
    )
    return CreateInviteResponse(
        invite_id=invite.invite_id,
        email=invite.email,
        role=invite.role,
        expires_at=invite.expires_at,
        token=invite.token,
        accept_path=ACCEPT_PATH + quote(invite.token),
    )


@router.delete("/{invite_id}", response_model=RevokeInviteResponse)
def revoke_invite(invite_id: UUID, user: OwnerDep, db: DbSession) -> RevokeInviteResponse:
    try:
        service.revoke_invite(db, restaurant_id=user.restaurant_id, invite_id=invite_id)
    except service.InviteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_ERROR) from exc
    except service.InviteStorageError as exc:
        raise _storage_error(exc) from exc

    logger.info("Invite revoked (invite_id=%s, restaurant_id=%s)", invite_id, user.restaurant_id)
    return RevokeInviteResponse()


@router.post("/accept", response_model=AcceptInviteResponse, status_code=status.HTTP_201_CREATED)
def accept_invite(payload: AcceptInviteRequest, db: DbSession) -> AcceptInviteResponse:
    """Public: the invited person is not logged in yet. The token is the proof of the invite."""
    try:
        accepted = service.accept_invite(
            db,
            token=payload.token,
            password=payload.password,
            eula_accepted=payload.eula_accepted,
            eula_version=payload.eula_version,
        )
    except service.InvitePolicyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except service.InvalidInviteError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=INVALID_INVITE_ERROR) from exc
    except service.AccountAlreadyExistsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=ACCOUNT_EXISTS_ERROR) from exc
    except service.InviteStorageError as exc:
        raise _storage_error(exc) from exc

    logger.info(
        "Invite accepted (user_id=%s, restaurant_id=%s, role=%s)",
        accepted.user_id,
        accepted.restaurant_id,
        accepted.role,
    )
    return AcceptInviteResponse(
        user_id=accepted.user_id,
        restaurant_id=accepted.restaurant_id,
        email=accepted.email,
        role=accepted.role,
    )
