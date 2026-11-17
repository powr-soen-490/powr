# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Authenticated encryption and POS persistence tests without external services."""

import base64
from collections.abc import Iterator
from datetime import datetime

import pytest
from pydantic import PostgresDsn, SecretStr, ValidationError
from pydantic_settings import SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core import encryption
from app.core.config import Settings
from app.modules.pos import service
from app.schemas.pos import PosCredentialsResponse

CONTEXT = "pos_credentials:TOAST:client_secret"
TEST_KEY = base64.urlsafe_b64encode(bytes(range(32))).decode()


class EncryptionTestSettings(Settings):
    """Keep encryption tests independent of the repository's local .env file."""

    model_config = SettingsConfigDict(env_file=None)


@pytest.fixture(autouse=True)
def encryption_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = EncryptionTestSettings(
        database_url=PostgresDsn("postgresql://powr:powr@localhost/powr_test"),
        pos_credentials_encryption_key=SecretStr(TEST_KEY),
    )
    monkeypatch.setattr(encryption, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("""
            CREATE TABLE pos_credentials (
                id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
                pos_name TEXT UNIQUE NOT NULL,
                client_id TEXT NOT NULL,
                client_secret TEXT NOT NULL,
                access_token TEXT,
                expires_at TEXT,
                needs_reconnect BOOLEAN NOT NULL DEFAULT 0
            )
        """)
        )
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


@pytest.mark.parametrize("value", ["client-secret", "", "sëcret 🔑"])
def test_encryption_round_trip_uses_distinct_nonces(value: str) -> None:
    first = encryption.encrypt_secret(value, context=CONTEXT)
    second = encryption.encrypt_secret(value, context=CONTEXT)

    assert first.startswith(encryption.ENVELOPE_PREFIX)
    assert first != second
    assert encryption.decrypt_secret(first, context=CONTEXT) == value
    assert encryption.decrypt_secret(second, context=CONTEXT) == value


@pytest.mark.parametrize("offset", [0, 12, -1])
def test_nonce_ciphertext_and_tag_tampering_are_rejected(offset: int) -> None:
    encrypted = encryption.encrypt_secret("client-secret", context=CONTEXT)
    payload = bytearray(base64.urlsafe_b64decode(encrypted[len(encryption.ENVELOPE_PREFIX) :]))
    payload[offset] ^= 1
    tampered = encryption.ENVELOPE_PREFIX + base64.urlsafe_b64encode(payload).decode()

    with pytest.raises(encryption.SecretEncryptionError):
        encryption.decrypt_secret(tampered, context=CONTEXT)


@pytest.mark.parametrize(
    "context", ["pos_credentials:SQUARE:client_secret", "pos_credentials:TOAST:access_token"]
)
def test_encrypted_values_cannot_be_swapped_between_providers_or_fields(context: str) -> None:
    encrypted = encryption.encrypt_secret("client-secret", context=CONTEXT)

    with pytest.raises(encryption.SecretEncryptionError):
        encryption.decrypt_secret(encrypted, context=context)


def test_wrong_key_is_rejected(encryption_settings: Settings) -> None:
    encrypted = encryption.encrypt_secret("client-secret", context=CONTEXT)
    encryption_settings.pos_credentials_encryption_key = SecretStr(
        base64.urlsafe_b64encode(bytes(reversed(range(32)))).decode()
    )

    with pytest.raises(encryption.SecretEncryptionError):
        encryption.decrypt_secret(encrypted, context=CONTEXT)


@pytest.mark.parametrize(
    "value", ["plaintext-secret", "aes256gcm:v2:AAAA", "aes256gcm:v1:@@@", "aes256gcm:v1:AAAA"]
)
def test_plaintext_unknown_versions_and_malformed_values_are_rejected(value: str) -> None:
    with pytest.raises(encryption.SecretEncryptionError):
        encryption.decrypt_secret(value, context=CONTEXT)


@pytest.mark.parametrize("value", ["not base64", "", base64.urlsafe_b64encode(bytes(16)).decode()])
def test_invalid_keys_are_rejected_without_exposing_the_key(value: str) -> None:
    with pytest.raises(ValidationError) as raised:
        EncryptionTestSettings(
            database_url=PostgresDsn("postgresql://powr:powr@localhost/powr_test"),
            pos_credentials_encryption_key=SecretStr(value),
        )
    assert "input_value" not in str(raised.value)


def test_insert_and_get_encrypt_storage_and_keep_http_responses_secret_free(db: Session) -> None:
    service.save_credentials(db, pos_name="TOAST", client_id="client", client_secret="secret")
    service.save_access_token(
        db, pos_name="TOAST", client_id="client", access_token="token", expires_at=None
    )
    stored = db.execute(text("SELECT * FROM pos_credentials")).mappings().one()
    assert stored["client_secret"] != "secret"
    assert stored["access_token"] != "token"

    decrypted = service.get_credentials(db, "TOAST")
    assert decrypted is not None
    assert decrypted["client_secret"] == "secret"
    assert decrypted["access_token"] == "token"
    response = PosCredentialsResponse.model_validate(decrypted).model_dump()
    assert set(response) == {"id", "pos_name", "client_id", "needs_reconnect"}


def test_edit_encrypts_the_new_secret_and_forgets_the_old_login(db: Session) -> None:
    service.save_credentials(db, pos_name="TOAST", client_id="client", client_secret="secret")
    service.save_access_token(
        db, pos_name="TOAST", client_id="client", access_token="token", expires_at=None
    )
    service.mark_needs_reconnect(db, pos_name="TOAST", client_id="client")

    service.update_credentials(db, pos_name="TOAST", client_id="updated", client_secret="latest")

    stored = db.execute(text("SELECT * FROM pos_credentials")).mappings().one()
    assert stored["client_secret"].startswith(encryption.ENVELOPE_PREFIX)
    decrypted = service.get_credentials(db, "TOAST")
    assert decrypted is not None
    assert decrypted["client_secret"] == "latest"
    assert decrypted["access_token"] is None
    assert not decrypted["needs_reconnect"]


def test_null_access_token_is_supported(db: Session) -> None:
    service.save_credentials(db, pos_name="TOAST", client_id="client", client_secret="secret")
    decrypted = service.get_credentials(db, "TOAST")
    assert decrypted is not None
    assert decrypted["access_token"] is None


def test_missing_key_prevents_writes_but_allows_metadata_reads(
    db: Session, encryption_settings: Settings
) -> None:
    encryption_settings.pos_credentials_encryption_key = None
    with pytest.raises(service.CredentialsStorageError):
        service.save_credentials(db, pos_name="TOAST", client_id="client", client_secret="secret")
    assert db.execute(text("SELECT count(*) FROM pos_credentials")).scalar_one() == 0
    assert service.list_credentials(db) == []


def test_tampered_database_values_fail_closed(db: Session) -> None:
    service.save_credentials(db, pos_name="TOAST", client_id="client", client_secret="secret")
    db.execute(text("UPDATE pos_credentials SET client_secret = 'plaintext-secret'"))
    db.commit()
    with pytest.raises(service.CredentialsStorageError):
        service.get_credentials(db, "TOAST")


def test_a_login_token_is_saved_encrypted(db: Session) -> None:
    # The expiry's time zone needs PostgreSQL; see tests/integration/test_toast_token_storage.py.
    service.save_credentials(db, pos_name="TOAST", client_id="client", client_secret="secret")

    saved = service.save_access_token(
        db, pos_name="TOAST", client_id="client", access_token="token", expires_at=None
    )

    assert saved is True
    stored = db.execute(text("SELECT access_token FROM pos_credentials")).scalar_one()
    assert stored.startswith(encryption.ENVELOPE_PREFIX)
    decrypted = service.get_credentials(db, "TOAST")
    assert decrypted is not None
    assert decrypted["access_token"] == "token"


def test_a_token_from_replaced_credentials_is_not_saved(db: Session) -> None:
    service.save_credentials(db, pos_name="TOAST", client_id="new-client", client_secret="secret")
    service.save_access_token(
        db, pos_name="TOAST", client_id="new-client", access_token="new", expires_at=None
    )

    saved = service.save_access_token(
        db, pos_name="TOAST", client_id="old-client", access_token="old", expires_at=None
    )

    assert saved is False
    decrypted = service.get_credentials(db, "TOAST")
    assert decrypted is not None
    assert decrypted["access_token"] == "new"


def test_an_expiry_without_a_time_zone_is_refused(db: Session) -> None:
    service.save_credentials(db, pos_name="TOAST", client_id="client", client_secret="secret")

    with pytest.raises(ValueError, match="timezone-aware"):
        service.save_access_token(
            db,
            pos_name="TOAST",
            client_id="client",
            access_token="token",
            expires_at=datetime(2026, 11, 17, 20, 0),
        )


def test_rejected_credentials_need_a_reconnect_and_lose_their_token(db: Session) -> None:
    service.save_credentials(db, pos_name="TOAST", client_id="client", client_secret="secret")
    service.save_access_token(
        db, pos_name="TOAST", client_id="client", access_token="token", expires_at=None
    )

    assert service.mark_needs_reconnect(db, pos_name="TOAST", client_id="client") is True

    stored = service.get_credentials(db, "TOAST")
    assert stored is not None
    assert stored["needs_reconnect"]
    assert stored["access_token"] is None


def test_replaced_credentials_are_not_flagged_by_an_old_login(db: Session) -> None:
    service.save_credentials(db, pos_name="TOAST", client_id="new-client", client_secret="secret")

    assert service.mark_needs_reconnect(db, pos_name="TOAST", client_id="old-client") is False

    stored = service.get_credentials(db, "TOAST")
    assert stored is not None
    assert not stored["needs_reconnect"]
