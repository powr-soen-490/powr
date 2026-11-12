# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""POS credential rules and transactions, independent of HTTP handling."""

from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.encryption import SecretEncryptionError, decrypt_secret, encrypt_secret
from app.modules.pos import repository


class CredentialsAlreadyExistError(Exception):
    """Credentials have already been configured for the provider."""


class CredentialsIntegrityError(Exception):
    """The database rejected the credentials because of an integrity constraint."""


class CredentialsStorageError(Exception):
    """The credentials could not be stored due to a database failure."""


class CredentialsNotFoundError(Exception):
    """The credentials for the provider were not found in the database."""


def get_credentials(db: Session, pos_name: str) -> dict[str, Any] | None:
    """Decrypt secrets for server-side integrations; HTTP response models exclude them."""
    try:
        row = repository.get_credentials(db, pos_name)
        if row is None:
            return None
        for field in ("client_secret", "access_token"):
            if row[field] is not None:
                row[field] = decrypt_secret(
                    row[field], context=f"pos_credentials:{pos_name}:{field}"
                )
        return row
    except (SQLAlchemyError, SecretEncryptionError) as exc:
        db.rollback()
        raise CredentialsStorageError from exc


def list_credentials(db: Session) -> list[dict[str, Any]]:
    """List all configured providers without their secrets or access tokens."""
    try:
        return repository.list_credentials(db)
    except SQLAlchemyError as exc:
        db.rollback()
        raise CredentialsStorageError from exc


def save_credentials(
    db: Session,
    *,
    pos_name: str,
    client_id: str,
    client_secret: str,
    access_token: str | None = None,
    expires_at: datetime | None = None,
) -> None:
    try:
        if repository.credentials_exist(db, pos_name):
            raise CredentialsAlreadyExistError
        repository.insert_credentials(
            db,
            pos_name=pos_name,
            client_id=client_id,
            encrypted_client_secret=encrypt_secret(
                client_secret, context=f"pos_credentials:{pos_name}:client_secret"
            ),
            encrypted_access_token=_encrypt_field(access_token, pos_name, "access_token"),
            expires_at=expires_at,
        )
        db.commit()
    except CredentialsAlreadyExistError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise CredentialsIntegrityError from exc
    except (SQLAlchemyError, SecretEncryptionError) as exc:
        db.rollback()
        raise CredentialsStorageError from exc


def update_credentials(
    db: Session,
    *,
    pos_name: str,
    client_id: str,
    client_secret: str,
    access_token: str | None = None,
    expires_at: datetime | None = None,
) -> None:
    try:
        if not repository.credentials_exist(db, pos_name):
            raise CredentialsNotFoundError
        repository.update_credentials(
            db,
            pos_name=pos_name,
            client_id=client_id,
            encrypted_client_secret=encrypt_secret(
                client_secret, context=f"pos_credentials:{pos_name}:client_secret"
            ),
            encrypted_access_token=_encrypt_field(access_token, pos_name, "access_token"),
            expires_at=expires_at,
        )
        db.commit()
    except CredentialsNotFoundError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise CredentialsIntegrityError from exc
    except (SQLAlchemyError, SecretEncryptionError) as exc:
        db.rollback()
        raise CredentialsStorageError from exc


def _encrypt_field(value: str | None, pos_name: str, field: str) -> str | None:
    if value is None:
        return None
    return encrypt_secret(value, context=f"pos_credentials:{pos_name}:{field}")


def delete_credentials(db: Session, *, pos_name: str) -> None:
    try:
        if not repository.credentials_exist(db, pos_name):
            raise CredentialsNotFoundError
        repository.delete_credentials(db, pos_name=pos_name)
        db.commit()
    except CredentialsNotFoundError:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise CredentialsStorageError from exc
