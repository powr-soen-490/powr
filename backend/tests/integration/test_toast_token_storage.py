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
from app.integrations.pos.toast.token_store import MemoryTokenStore, ToastToken
from app.modules.pos import repository, service, toast_tokens
from app.modules.pos.toast_tokens import SavedToastTokenStore, script_token_store

EXPIRES_AT = datetime(2026, 11, 17, 20, 0, tzinfo=UTC)


KEY = SecretStr(base64.urlsafe_b64encode(bytes(range(32))).decode())


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None, pos_credentials_encryption_key=KEY)
    monkeypatch.setattr(encryption, "get_settings", lambda: settings)


def scripts_use(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    """Point script_token_store at this database, like a script reading .env."""
    settings = Settings(
        _env_file=None, database_url=database_url, pos_credentials_encryption_key=KEY
    )
    monkeypatch.setattr(toast_tokens, "get_settings", lambda: settings)


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


def test_a_script_with_the_apps_client_id_reuses_and_saves_the_token(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(migrated_engine) as db:
        connect(db, "client")
        service.save_access_token(
            db, pos_name="TOAST", client_id="client", access_token="t", expires_at=EXPIRES_AT
        )
    scripts_use(monkeypatch, migrated_engine.url.render_as_string(hide_password=False))

    with script_token_store("client") as store:
        assert isinstance(store, SavedToastTokenStore)
        assert store.load() == ToastToken(access_token="t", expires_at=EXPIRES_AT)
        store.save(ToastToken(access_token="new", expires_at=EXPIRES_AT))

    with Session(migrated_engine) as db:
        stored = service.get_credentials(db, "TOAST")
    assert stored is not None
    assert stored["access_token"] == "new"


def test_a_script_with_another_client_id_keeps_its_token_to_itself(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(migrated_engine) as db:
        connect(db, "the-apps-client")
    scripts_use(monkeypatch, migrated_engine.url.render_as_string(hide_password=False))

    with script_token_store("a-developers-client") as store:
        assert isinstance(store, MemoryTokenStore)
        store.save(ToastToken(access_token="dev", expires_at=None))

    with Session(migrated_engine) as db:
        stored = service.get_credentials(db, "TOAST")
    assert stored is not None
    assert stored["access_token"] is None


def test_a_script_without_a_database_still_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    # Port 1 refuses connections, like a laptop where the database is not started.
    scripts_use(monkeypatch, "postgresql://powr:powr@127.0.0.1:1/powr")

    with script_token_store("client") as store:
        assert isinstance(store, MemoryTokenStore)


def test_the_saved_store_reads_a_token_another_request_saved(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as db:
        connect(db, "client")
        first = ToastToken(access_token="first", expires_at=EXPIRES_AT)
        store = SavedToastTokenStore(db, client_id="client", token=first)
        assert store.load() == first  # read with the credentials: no extra query

        with Session(migrated_engine) as other:
            service.save_access_token(
                other, pos_name="TOAST", client_id="client", access_token="newer", expires_at=None
            )

        assert store.load() == ToastToken(access_token="newer", expires_at=None)


def test_the_saved_store_has_nothing_to_reuse_after_a_reconnect(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as db:
        connect(db, "old-client")
        store = SavedToastTokenStore(db, client_id="old-client", token=None)
        store.load()
        connect(db, "new-client")

        assert store.load() is None
