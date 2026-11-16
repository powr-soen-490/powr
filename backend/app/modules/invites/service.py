# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Invite rules: create, revoke and accept one-time invite links. No HTTP handling here.

The raw token is shown to the owner once and never stored: the database keeps only its
SHA-256 hash. A fast hash is enough here because the token is 32 random bytes, so it cannot be
guessed the way a password can (see the OWASP Forgot Password Cheat Sheet).
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password, validate_password_policy
from app.modules.invites import repository

INVITE_VALID_HOURS = 72
# Same value as app.core.auth.KITCHEN_MANAGER; not imported, so this module stays free of FastAPI.
KITCHEN_MANAGER = "kitchen_manager"
TOKEN_BYTES = 32


class InviteError(Exception):
    """Base class for invite errors the API turns into HTTP responses."""


class AccountAlreadyExistsError(InviteError):
    """The invited email already has a powr account."""


class InviteNotFoundError(InviteError):
    """No pending invite with this id in the caller's restaurant."""


class InvalidInviteError(InviteError):
    """The link is unknown, expired, revoked or already used."""


class InvitePolicyError(InviteError):
    """The request breaks a rule, e.g. the EULA was not accepted or the password is weak."""


class InviteStorageError(InviteError):
    """The database failed while handling the invite."""


@dataclass(frozen=True)
class CreatedInvite:
    invite_id: UUID
    email: str
    role: str
    expires_at: datetime
    token: str


@dataclass(frozen=True)
class AcceptedInvite:
    user_id: UUID
    restaurant_id: UUID
    email: str
    role: str


def generate_invite_token() -> str:
    """A URL-safe token with 256 bits of randomness."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_invite(db: Session, *, restaurant_id: UUID, email: str) -> CreatedInvite:
    """Creates a kitchen-manager invite and returns the raw token (shown to the owner once).

    An older unused invite for the same email in this restaurant is revoked, so only the newest
    link works.
    """
    normalized_email = email.strip().lower()
    token = generate_invite_token()
    try:
        if repository.user_exists(db, normalized_email):
            raise AccountAlreadyExistsError
        repository.revoke_pending_for_email(db, restaurant_id, normalized_email)
        row = repository.insert_invite(
            db,
            restaurant_id=restaurant_id,
            email=normalized_email,
            role=KITCHEN_MANAGER,
            token_hash=hash_invite_token(token),
            valid_hours=INVITE_VALID_HOURS,
        )
        db.commit()
    except InviteError:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise InviteStorageError from exc

    return CreatedInvite(
        invite_id=row["id"],
        email=row["email"],
        role=row["role"],
        expires_at=row["expires_at"],
        token=token,
    )


def revoke_invite(db: Session, *, restaurant_id: UUID, invite_id: UUID) -> None:
    try:
        revoked = repository.revoke_invite(db, restaurant_id, invite_id)
        if not revoked:
            raise InviteNotFoundError
        db.commit()
    except InviteError:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise InviteStorageError from exc


def accept_invite(
    db: Session,
    *,
    token: str,
    password: str,
    eula_accepted: bool,
    eula_version: str,
) -> AcceptedInvite:
    """Uses the link: creates the account, its membership and the EULA acceptance together.

    The request is checked before the link is used, so a weak password does not burn the link.
    Everything runs in one transaction: if creating the account fails, the link stays unused.
    """
    if not eula_accepted:
        raise InvitePolicyError("EULA acceptance is required to create an account.")
    try:
        validate_password_policy(password)
    except ValueError as exc:
        raise InvitePolicyError(str(exc)) from exc

    try:
        invite = repository.claim_invite(db, hash_invite_token(token))
        if invite is None:
            raise InvalidInviteError
        user_id = repository.insert_user(db, invite["email"], hash_password(password))
        repository.insert_membership(db, invite["restaurant_id"], user_id, invite["role"])
        repository.insert_eula_acceptance(db, user_id, eula_version)
        db.commit()
    except InviteError:
        db.rollback()
        raise
    except IntegrityError as exc:
        # Someone created an account with this email after the invite was sent.
        db.rollback()
        raise AccountAlreadyExistsError from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise InviteStorageError from exc

    return AcceptedInvite(
        user_id=user_id,
        restaurant_id=invite["restaurant_id"],
        email=invite["email"],
        role=invite["role"],
    )
