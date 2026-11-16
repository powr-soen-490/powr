# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Database queries for shared POS provider credentials and each restaurant's POS connection."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.integrations.pos.models import PosConnection


def get_connection(db: Session, restaurant_id: UUID, provider: str) -> PosConnection | None:
    row = db.execute(
        text("""
            SELECT id, restaurant_id, provider, location_id
            FROM pos_connections
            WHERE restaurant_id = :restaurant_id AND provider = :provider
            LIMIT 1
        """),
        {"restaurant_id": restaurant_id, "provider": provider},
    ).first()
    if row is None:
        return None
    return PosConnection(
        id=UUID(str(row[0])),
        restaurant_id=UUID(str(row[1])),
        provider=row[2],
        location_id=row[3],
    )


def get_connection_details(
    db: Session, restaurant_id: UUID, provider: str
) -> dict[str, Any] | None:
    row = (
        db.execute(
            text("""
                SELECT location_id, location_name
                FROM pos_connections
                WHERE restaurant_id = :restaurant_id AND provider = :provider
            """),
            {"restaurant_id": restaurant_id, "provider": provider},
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def save_connection(
    db: Session, *, restaurant_id: UUID, provider: str, location_id: str, location_name: str
) -> None:
    """Link the restaurant to a POS location, replacing the location it was linked to before."""
    db.execute(
        text("""
            INSERT INTO pos_connections (restaurant_id, provider, location_id, location_name)
            VALUES (:restaurant_id, :provider, :location_id, :location_name)
            ON CONFLICT (restaurant_id, provider) DO UPDATE
            SET location_id = EXCLUDED.location_id, location_name = EXCLUDED.location_name
        """),
        {
            "restaurant_id": restaurant_id,
            "provider": provider,
            "location_id": location_id,
            "location_name": location_name,
        },
    )


def any_connection(db: Session, *, provider: str) -> bool:
    """Whether any restaurant is still connected to the provider."""
    row = db.execute(
        text("SELECT 1 FROM pos_connections WHERE provider = :provider LIMIT 1"),
        {"provider": provider},
    ).first()
    return row is not None


def delete_connection(db: Session, *, restaurant_id: UUID, provider: str) -> None:
    db.execute(
        text("""
            DELETE FROM pos_connections
            WHERE restaurant_id = :restaurant_id AND provider = :provider
        """),
        {"restaurant_id": restaurant_id, "provider": provider},
    )


def replace_credentials(
    db: Session, *, pos_name: str, client_id: str, encrypted_client_secret: str
) -> None:
    """Save new credentials and forget the old access token, which belonged to the old ones."""
    db.execute(
        text("""
            INSERT INTO pos_credentials (pos_name, client_id, client_secret)
            VALUES (:pos_name, :client_id, :client_secret)
            ON CONFLICT (pos_name) DO UPDATE
            SET client_id = EXCLUDED.client_id, client_secret = EXCLUDED.client_secret,
                access_token = NULL, expires_at = NULL
        """),
        {
            "pos_name": pos_name,
            "client_id": client_id,
            "client_secret": encrypted_client_secret,
        },
    )


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
