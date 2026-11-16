# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Database queries for invites. Every query is scoped to a restaurant or to one token hash."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def user_exists(db: Session, email: str) -> bool:
    row = db.execute(
        text("SELECT 1 FROM users WHERE LOWER(email) = :email"),
        {"email": email},
    ).first()
    return row is not None


def revoke_pending_for_email(db: Session, restaurant_id: UUID, email: str) -> None:
    """Revokes this restaurant's unused invites for the email, so only the newest link works."""
    db.execute(
        text("""
            UPDATE invites
            SET revoked_at = NOW()
            WHERE restaurant_id = :restaurant_id
              AND email = :email
              AND revoked_at IS NULL
              AND accepted_at IS NULL
        """),
        {"restaurant_id": restaurant_id, "email": email},
    )


def insert_invite(
    db: Session,
    *,
    restaurant_id: UUID,
    email: str,
    role: str,
    token_hash: str,
    valid_hours: int,
) -> dict[str, Any]:
    row = db.execute(
        text("""
            INSERT INTO invites (restaurant_id, email, role, token_hash, expires_at)
            VALUES (
                :restaurant_id, :email, :role, :token_hash,
                NOW() + make_interval(hours => :valid_hours)
            )
            RETURNING id, email, role, expires_at
        """),
        {
            "restaurant_id": restaurant_id,
            "email": email,
            "role": role,
            "token_hash": token_hash,
            "valid_hours": valid_hours,
        },
    ).one()
    return dict(row._mapping)


def revoke_invite(db: Session, restaurant_id: UUID, invite_id: UUID) -> bool:
    """Revokes a pending invite of this restaurant. False if there is no such pending invite."""
    row = db.execute(
        text("""
            UPDATE invites
            SET revoked_at = NOW()
            WHERE id = :invite_id
              AND restaurant_id = :restaurant_id
              AND revoked_at IS NULL
              AND accepted_at IS NULL
            RETURNING id
        """),
        {"invite_id": invite_id, "restaurant_id": restaurant_id},
    ).first()
    return row is not None


def claim_invite(db: Session, token_hash: str) -> dict[str, Any] | None:
    """Marks a valid invite as used and returns it, in one statement.

    The WHERE clause and the update run together, so if the same link is accepted twice at the
    same time, only one request gets the row back. Returns None when the link is unknown,
    expired, revoked or already used.
    """
    row = db.execute(
        text("""
            UPDATE invites
            SET accepted_at = NOW()
            WHERE token_hash = :token_hash
              AND accepted_at IS NULL
              AND revoked_at IS NULL
              AND expires_at > NOW()
            RETURNING id, restaurant_id, email, role
        """),
        {"token_hash": token_hash},
    ).first()
    return None if row is None else dict(row._mapping)


def insert_user(db: Session, email: str, password_hash: str) -> UUID:
    row = db.execute(
        text("""
            INSERT INTO users (email, password_hash)
            VALUES (:email, :password_hash)
            RETURNING id
        """),
        {"email": email, "password_hash": password_hash},
    ).one()
    user_id: UUID = row.id
    return user_id


def insert_membership(db: Session, restaurant_id: UUID, user_id: UUID, role: str) -> None:
    db.execute(
        text("""
            INSERT INTO restaurant_memberships (restaurant_id, user_id, role)
            VALUES (:restaurant_id, :user_id, :role)
        """),
        {"restaurant_id": restaurant_id, "user_id": user_id, "role": role},
    )


def insert_eula_acceptance(db: Session, user_id: UUID, eula_version: str) -> None:
    db.execute(
        text("""
            INSERT INTO eula_acceptances (user_id, eula_version)
            VALUES (:user_id, :eula_version)
        """),
        {"user_id": user_id, "eula_version": eula_version},
    )
