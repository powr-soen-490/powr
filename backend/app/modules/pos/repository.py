# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Database queries for shared POS provider credentials."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def credentials_exist(db: Session, pos_name: str) -> bool:
    row = db.execute(
        text("SELECT id FROM pos_credentials WHERE pos_name = :pos_name"),
        {"pos_name": pos_name},
    ).fetchone()
    return row is not None


def get_credentials(db: Session, pos_name: str) -> dict[str, Any] | None:
    row = (
        db.execute(
            text("""
            SELECT id, pos_name, client_id, client_secret, access_token, expires_at
            FROM pos_credentials
            WHERE pos_name = :pos_name
        """),
            {"pos_name": pos_name},
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def list_credentials(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            text("""
            SELECT id, pos_name, client_id, expires_at
            FROM pos_credentials
            ORDER BY pos_name, id
        """)
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def insert_credentials(
    db: Session,
    *,
    pos_name: str,
    client_id: str,
    encrypted_client_secret: str,
    encrypted_access_token: str | None = None,
    expires_at: datetime | None = None,
) -> None:
    db.execute(
        text("""
            INSERT INTO pos_credentials
                (pos_name, client_id, client_secret, access_token, expires_at)
            VALUES (:pos_name, :client_id, :client_secret, :access_token, :expires_at)
        """),
        {
            "pos_name": pos_name,
            "client_id": client_id,
            "client_secret": encrypted_client_secret,
            "access_token": encrypted_access_token,
            "expires_at": expires_at,
        },
    )


def update_credentials(
    db: Session,
    *,
    pos_name: str,
    client_id: str,
    encrypted_client_secret: str,
    encrypted_access_token: str | None = None,
    expires_at: datetime | None = None,
) -> None:
    db.execute(
        text("""
            UPDATE pos_credentials
            SET client_id = :client_id, client_secret = :client_secret,
                access_token = COALESCE(:access_token, access_token),
                expires_at = COALESCE(:expires_at, expires_at)
            WHERE pos_name = :pos_name
        """),
        {
            "pos_name": pos_name,
            "client_id": client_id,
            "client_secret": encrypted_client_secret,
            "access_token": encrypted_access_token,
            "expires_at": expires_at,
        },
    )


def credentials_for_encryption(db: Session) -> list[dict[str, Any]]:
    """Lock existing rows for the explicit plaintext-to-ciphertext migration."""
    rows = (
        db.execute(
            text("SELECT id, pos_name, client_secret, access_token FROM pos_credentials FOR UPDATE")
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def replace_encrypted_secrets(
    db: Session, *, credential_id: UUID, client_secret: str, access_token: str | None
) -> None:
    db.execute(
        text("""
            UPDATE pos_credentials
            SET client_secret = :client_secret, access_token = :access_token
            WHERE id = :id
        """),
        {"id": credential_id, "client_secret": client_secret, "access_token": access_token},
    )


def delete_credentials(db: Session, pos_name: str) -> None:
    db.execute(
        text("DELETE FROM pos_credentials WHERE pos_name = :pos_name"),
        {"pos_name": pos_name},
    )
