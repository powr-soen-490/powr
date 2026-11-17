# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Connecting Toast end to end: real owner sessions, a real database and a fake Toast."""

import base64
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, text

from app.api import toast_connection
from app.core import encryption
from app.core.config import Settings
from app.core.database import migrate_up
from app.core.encryption import decrypt_secret
from app.integrations.pos.models import PosLocation
from app.integrations.pos.toast.client import ToastCredentials
from app.integrations.pos.toast.locations import RESTAURANTS_PATH, find_toast_locations
from app.integrations.pos.toast.token_store import ToastTokenStore
from tests.unit.toast_fakes import BASE_URL, FakeToast

CONNECTION = "/api/pos/toast/connection"
SECRET = "private-client-secret"


@pytest.fixture(autouse=True)
def fake_toast_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    key = SecretStr(base64.urlsafe_b64encode(bytes(range(32))).decode())
    settings = Settings(_env_file=None, pos_credentials_encryption_key=key)
    monkeypatch.setattr(encryption, "get_settings", lambda: settings)
    toast = FakeToast()
    toast.reply(
        RESTAURANTS_PATH,
        httpx2.Response(
            200, json=[{"restaurantGuid": "guid-1", "restaurantName": "Mykonos Grill - Boca NEW"}]
        ),
    )

    def find_with_fake_toast(
        credentials: ToastCredentials,
        *,
        base_url: str,
        transport: object = None,
        token_store: ToastTokenStore | None = None,
    ) -> list[PosLocation]:
        return find_toast_locations(
            credentials,
            base_url=BASE_URL,
            transport=httpx2.MockTransport(toast._handle),
            sleep=toast.sleep,
            clock=toast.clock,
            token_store=token_store,
        )

    monkeypatch.setattr(toast_connection, "find_toast_locations", find_with_fake_toast)


def stored(engine: Engine) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with engine.connect() as db:
        connections = db.execute(
            text("SELECT restaurant_id, location_id, location_name FROM pos_connections")
        ).mappings()
        credentials = db.execute(
            text("SELECT pos_name, client_id, client_secret FROM pos_credentials")
        ).mappings()
        return [dict(row) for row in connections], [dict(row) for row in credentials]


def test_owner_connects_sees_only_their_restaurant_and_disconnects(
    make_client: Callable[[], TestClient],
    sign_up_owner: Callable[[TestClient, str], dict[str, Any]],
    migrated_engine: Engine,
) -> None:
    owner = make_client()
    restaurant_id = sign_up_owner(owner, "owner@example.com")["restaurant_id"]
    other = make_client()
    sign_up_owner(other, "other@example.com")

    response = owner.put(CONNECTION, json={"client_id": "my-client", "client_secret": SECRET})

    assert response.status_code == 200, response.text
    connections, credentials = stored(migrated_engine)
    assert [
        (str(row["restaurant_id"]), row["location_id"], row["location_name"]) for row in connections
    ] == [(restaurant_id, "guid-1", "Mykonos Grill - Boca NEW")]
    [saved] = credentials
    assert (saved["pos_name"], saved["client_id"]) == ("TOAST", "my-client")
    assert SECRET not in saved["client_secret"]
    assert (
        decrypt_secret(saved["client_secret"], context="pos_credentials:TOAST:client_secret")
        == SECRET
    )

    assert owner.get(CONNECTION).json() == {
        "location_id": "guid-1",
        "location_name": "Mykonos Grill - Boca NEW",
    }
    assert other.get(CONNECTION).status_code == 404

    # Connecting again replaces the restaurant's link instead of adding a second one.
    assert (
        owner.put(CONNECTION, json={"client_id": "new-client", "client_secret": SECRET}).status_code
        == 200
    )
    connections, credentials = stored(migrated_engine)
    assert len(connections) == 1
    assert [row["client_id"] for row in credentials] == ["new-client"]

    assert owner.delete(CONNECTION).status_code == 200
    assert stored(migrated_engine) == ([], [])
    assert owner.get(CONNECTION).status_code == 404


def test_disconnecting_one_restaurant_keeps_the_login_for_the_others(
    make_client: Callable[[], TestClient],
    sign_up_owner: Callable[[TestClient, str], dict[str, Any]],
    migrated_engine: Engine,
) -> None:
    first = make_client()
    sign_up_owner(first, "first@example.com")
    second = make_client()
    sign_up_owner(second, "second@example.com")
    body = {"client_id": "shared-client", "client_secret": SECRET}
    assert first.put(CONNECTION, json=body).status_code == 200
    assert second.put(CONNECTION, json=body).status_code == 200

    assert first.delete(CONNECTION).status_code == 200

    connections, credentials = stored(migrated_engine)
    assert len(connections) == 1
    assert [row["client_id"] for row in credentials] == ["shared-client"]
    assert first.get(CONNECTION).status_code == 404
    assert second.get(CONNECTION).status_code == 200

    assert second.delete(CONNECTION).status_code == 200
    assert stored(migrated_engine) == ([], [])


def test_location_name_migration_can_run_again(migrated_engine: Engine) -> None:
    migrate_up(migrated_engine)

    with migrated_engine.connect() as db:
        columns = db.execute(
            text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'pos_connections'"
            )
        ).scalars()
        assert "location_name" in set(columns)
