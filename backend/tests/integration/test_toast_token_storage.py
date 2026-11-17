# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""The saved Toast access token and the needs_reconnect flag in PostgreSQL (issue #173)."""

import base64
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core import encryption
from app.core.config import Settings
from app.core.database import migrate_up
from app.modules.pos import repository, service

EXPIRES_AT = datetime(2026, 11, 17, 20, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    key = SecretStr(base64.urlsafe_b64encode(bytes(range(32))).decode())
    settings = Settings(_env_file=None, pos_credentials_encryption_key=key)
    monkeypatch.setattr(encryption, "get_settings", lambda: settings)


def connect(db: Session, client_id: str) -> None:
    repository.replace_credentials(
        db,
        pos_name="TOAST",
        client_id=client_id,
        encrypted_client_secret=encryption.encrypt_secret(
            "secret", context="pos_credentials:TOAST:client_secret"
        ),
    )
    db.commit()


def test_expiry_keeps_its_time_zone_and_the_migration_can_run_again(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as db:
        connect(db, "client")
        service.save_access_token(
            db, pos_name="TOAST", client_id="client", access_token="t", expires_at=EXPIRES_AT
        )

    # Converting expires_at a second time would shift it by a non-UTC session time zone.
    montreal = create_engine(
        migrated_engine.url, connect_args={"options": "-c timezone=America/Montreal"}
    )
    try:
        migrate_up(montreal)
    finally:
        montreal.dispose()

    with Session(migrated_engine) as db:
        stored = service.get_credentials(db, "TOAST")
    assert stored is not None
    assert stored["expires_at"] == EXPIRES_AT
    assert stored["needs_reconnect"] is False


def test_reconnecting_clears_the_flag_and_the_old_token(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as db:
        connect(db, "old-client")
        service.save_access_token(
            db, pos_name="TOAST", client_id="old-client", access_token="t", expires_at=EXPIRES_AT
        )
        service.mark_needs_reconnect(db, pos_name="TOAST", client_id="old-client")

        connect(db, "new-client")

        stored = service.get_credentials(db, "TOAST")
    assert stored is not None
    assert stored["needs_reconnect"] is False
    assert stored["access_token"] is None
    assert stored["expires_at"] is None


def test_connecting_can_save_the_token_from_its_login(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as db:
        repository.replace_credentials(
            db,
            pos_name="TOAST",
            client_id="client",
            encrypted_client_secret=encryption.encrypt_secret(
                "secret", context="pos_credentials:TOAST:client_secret"
            ),
            encrypted_access_token=encryption.encrypt_secret(
                "token", context="pos_credentials:TOAST:access_token"
            ),
            expires_at=EXPIRES_AT,
        )
        db.commit()

        stored = service.get_credentials(db, "TOAST")
    assert stored is not None
    assert stored["access_token"] == "token"
    assert stored["expires_at"] == EXPIRES_AT
