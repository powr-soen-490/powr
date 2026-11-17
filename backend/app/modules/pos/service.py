# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""POS credential rules and transactions, independent of HTTP handling."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, TypedDict
from uuid import UUID

import httpx2
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.encryption import SecretEncryptionError, decrypt_secret, encrypt_secret
from app.integrations.pos.models import PosConnection, PosLocation, SaleLine
from app.integrations.pos.toast.client import (
    ToastApiError,
    ToastAuthenticationError,
    ToastCredentials,
    ToastRateLimitError,
)
from app.integrations.pos.toast.recorded import recorded_toast_transport
from app.modules.pos import repository

TOAST = "TOAST"


def toast_transport() -> httpx2.BaseTransport | None:
    """How requests reach Toast: None for the real API, or the recorded week when
    TOAST_USE_RECORDED_DATA is on for local development."""
    if get_settings().toast_use_recorded_data:
        return recorded_toast_transport()
    return None


# Lists the Toast restaurants some credentials can access (see integrations/pos/toast).
ToastLocationFinder = Callable[[ToastCredentials], list[PosLocation]]


class DailyAggregation(TypedDict):
    items: Decimal
    revenue: Decimal
    orders: set[str]


@dataclass(frozen=True)
class SalesAggregation:
    daily: dict[str, DailyAggregation]
    total_orders: int
    total_items: Decimal
    total_revenue: Decimal


def aggregate_sales(
    lines: Iterable[SaleLine], start_date: date, end_date: date
) -> SalesAggregation:
    """Summarize non-voided lines within the inclusive business-date window."""
    daily: dict[str, DailyAggregation] = {}
    for line in lines:
        if line.is_voided or not start_date <= line.business_date <= end_date:
            continue
        stat = daily.setdefault(
            str(line.business_date),
            DailyAggregation(items=Decimal("0"), revenue=Decimal("0"), orders=set()),
        )
        stat["items"] += line.quantity
        stat["revenue"] += line.price or Decimal("0")
        stat["orders"].add(line.order_id)
    order_ids: set[str] = set()
    for stat in daily.values():
        order_ids.update(stat["orders"])
    return SalesAggregation(
        daily=daily,
        total_orders=len(order_ids),
        total_items=sum((stat["items"] for stat in daily.values()), Decimal("0")),
        total_revenue=sum((stat["revenue"] for stat in daily.values()), Decimal("0")),
    )


class ConnectionStorageError(Exception):
    """The POS connection could not be read or saved because of a database failure."""


def get_connection(db: Session, restaurant_id: UUID, provider: str) -> PosConnection | None:
    try:
        return repository.get_connection(db, restaurant_id, provider)
    except SQLAlchemyError as exc:
        db.rollback()
        raise ConnectionStorageError from exc


class ToastConnectError(Exception):
    """Toast could not be connected; nothing was saved."""


class ToastLoginRejectedError(ToastConnectError):
    """Toast rejected the client ID or secret."""


class ToastBusyError(ToastConnectError):
    """Toast is limiting logins right now."""


class ToastUnavailableError(ToastConnectError):
    """Toast could not be reached or answered with an error."""


class NoToastRestaurantError(ToastConnectError):
    """The credentials work but cannot access any restaurant."""


class MultipleToastRestaurantsError(ToastConnectError):
    """The credentials can access several restaurants; picking one is planned in #161."""


def get_toast_connection(db: Session, restaurant_id: UUID) -> dict[str, Any] | None:
    """The restaurant's Toast location ID and name, or None when it is not connected."""
    try:
        return repository.get_connection_details(db, restaurant_id, TOAST)
    except SQLAlchemyError as exc:
        db.rollback()
        raise ConnectionStorageError from exc


def connect_toast(
    db: Session,
    *,
    restaurant_id: UUID,
    client_id: str,
    client_secret: str,
    find_locations: ToastLocationFinder,
) -> PosLocation:
    """Check the credentials with Toast, then save them with the restaurant they can access.

    Nothing is saved unless Toast accepts the credentials and they can access exactly one
    restaurant.
    """
    location = _find_one_toast_location(
        find_locations, ToastCredentials(client_id=client_id, client_secret=client_secret)
    )
    try:
        # pos_credentials holds one Toast login for the whole app, so connecting replaces it.
        # Per-restaurant logins are part of the connection model planned in #161.
        repository.replace_credentials(
            db,
            pos_name=TOAST,
            client_id=client_id,
            encrypted_client_secret=encrypt_secret(
                client_secret, context=f"pos_credentials:{TOAST}:client_secret"
            ),
        )
        repository.save_connection(
            db,
            restaurant_id=restaurant_id,
            provider=TOAST,
            location_id=location.location_id,
            location_name=location.name,
        )
        db.commit()
    except (SQLAlchemyError, SecretEncryptionError) as exc:
        db.rollback()
        raise ConnectionStorageError from exc
    return location


def disconnect_toast(db: Session, *, restaurant_id: UUID) -> None:
    """Remove the restaurant's Toast location, and the shared Toast login once nobody uses it.

    Other restaurants may still be connected with the shared login, so it is only deleted
    when this was the last Toast connection.
    """
    try:
        repository.delete_connection(db, restaurant_id=restaurant_id, provider=TOAST)
        if not repository.any_connection(db, provider=TOAST):
            repository.delete_credentials(db, pos_name=TOAST)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise ConnectionStorageError from exc


def _find_one_toast_location(
    find_locations: ToastLocationFinder, credentials: ToastCredentials
) -> PosLocation:
    try:
        locations = find_locations(credentials)
    except ToastAuthenticationError as exc:
        raise ToastLoginRejectedError from exc
    except ToastRateLimitError as exc:
        raise ToastBusyError from exc
    except ToastApiError as exc:
        raise ToastUnavailableError from exc
    if not locations:
        raise NoToastRestaurantError
    if len(locations) > 1:
        raise MultipleToastRestaurantsError
    return locations[0]


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
