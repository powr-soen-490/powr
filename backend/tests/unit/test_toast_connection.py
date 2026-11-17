# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Toast connection endpoint tests with signed sessions, a mock database and a fake Toast."""

import base64
from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import PostgresDsn, SecretStr
from pydantic_settings import SettingsConfigDict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import toast_connection
from app.core import encryption
from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import create_session_token
from app.integrations.pos.models import PosLocation
from app.integrations.pos.toast.client import LOGIN_PATH, ToastCredentials
from app.integrations.pos.toast.locations import RESTAURANTS_PATH, find_toast_locations
from tests.unit.toast_fakes import BASE_URL, FakeToast

CONNECTION = "/api/pos/toast/connection"
SECRET = "private-client-secret"
BODY = {"client_id": " my-client ", "client_secret": SECRET}
MYKONOS = {"restaurantGuid": "guid-1", "restaurantName": "Mykonos Grill - Boca NEW"}
SECOND_RESTAURANT = {"restaurantGuid": "guid-2", "restaurantName": "Another restaurant"}


class ConnectionTestSettings(Settings):
    """Keep these tests independent of local credentials and encryption keys."""

    model_config = SettingsConfigDict(env_file=None)


@pytest.fixture
def settings() -> Settings:
    return ConnectionTestSettings(
        database_url=PostgresDsn("postgresql://powr:powr@localhost/powr_test"),
        pos_credentials_encryption_key=SecretStr(
            base64.urlsafe_b64encode(bytes(range(32))).decode()
        ),
    )


class FakeDatabase:
    """A mock session that answers the session lookup and records every POS query."""

    def __init__(self, user: CurrentUser) -> None:
        self.user = user
        self.connection: dict[str, Any] | None = None
        # Whether another restaurant is still connected to Toast.
        self.others_connected = False
        self.pos_queries: list[tuple[str, dict[str, Any]]] = []
        # When set, every POS query fails as if the database were down.
        self.pos_error: SQLAlchemyError | None = None
        self.session = Mock(spec=Session)
        self.session.execute.side_effect = self._execute

    def _execute(self, query: Any, params: dict[str, Any] | None = None) -> Mock:
        sql = " ".join(str(query).split())
        result = Mock()
        if "restaurant_memberships" in sql:
            result.first.return_value = self.user
        else:
            if self.pos_error is not None:
                raise self.pos_error
            self.pos_queries.append((sql, params or {}))
            result.first.return_value = (1,) if self.others_connected else None
            result.mappings.return_value.first.return_value = self.connection
        return result

    def queries(self, start: str) -> list[dict[str, Any]]:
        return [params for sql, params in self.pos_queries if sql.startswith(start)]


@pytest.fixture
def toast() -> FakeToast:
    fake = FakeToast()
    fake.reply(RESTAURANTS_PATH, httpx2.Response(200, json=[MYKONOS]))
    return fake


def sign_in(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    toast: FakeToast,
    role: str,
) -> FakeDatabase:
    user = CurrentUser(uuid4(), "member@example.com", uuid4(), "Test restaurant", role)
    db = FakeDatabase(user)
    app.dependency_overrides[get_db] = lambda: db.session
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(encryption, "get_settings", lambda: settings)

    def find_with_fake_toast(
        credentials: ToastCredentials, *, base_url: str, transport: object = None
    ) -> list[PosLocation]:
        return find_toast_locations(
            credentials,
            base_url=BASE_URL,
            transport=httpx2.MockTransport(toast._handle),
            sleep=toast.sleep,
            clock=toast.clock,
        )

    monkeypatch.setattr(toast_connection, "find_toast_locations", find_with_fake_toast)
    client.cookies.set(
        settings.session_cookie_name,
        create_session_token(
            str(user.user_id),
            str(user.restaurant_id),
            role="owner",
            secret_key=settings.session_secret_key,
        ),
    )
    return db


@pytest.fixture
def owner(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    toast: FakeToast,
) -> Iterator[FakeDatabase]:
    yield sign_in(app, client, settings, monkeypatch, toast, "owner")
    app.dependency_overrides.clear()


def test_connect_finds_the_guid_and_saves_it_with_the_encrypted_secret(
    client: TestClient, owner: FakeDatabase, toast: FakeToast
) -> None:
    response = client.put(CONNECTION, json=BODY)

    assert response.status_code == 200, response.text
    assert response.json() == {"location_id": "guid-1", "location_name": "Mykonos Grill - Boca NEW"}
    [credentials] = owner.queries("INSERT INTO pos_credentials")
    assert credentials["client_id"] == "my-client"
    assert SECRET not in credentials["client_secret"]
    [connection] = owner.queries("INSERT INTO pos_connections")
    assert connection == {
        "restaurant_id": owner.user.restaurant_id,
        "provider": "TOAST",
        "location_id": "guid-1",
        "location_name": "Mykonos Grill - Boca NEW",
    }
    owner.session.commit.assert_called_once()
    [login] = toast.requests_to(LOGIN_PATH)
    assert b"my-client" in login.content
    assert SECRET not in response.text


@pytest.mark.parametrize(
    ("path", "reply", "status_code"),
    [
        (LOGIN_PATH, httpx2.Response(401, json={"status": 401}), 400),
        (RESTAURANTS_PATH, httpx2.Response(200, json=[]), 404),
        (RESTAURANTS_PATH, httpx2.Response(200, json=[MYKONOS, SECOND_RESTAURANT]), 409),
        (LOGIN_PATH, httpx2.Response(429), 429),
        (RESTAURANTS_PATH, httpx2.Response(503), 502),
        (RESTAURANTS_PATH, httpx2.ConnectError("offline"), 502),
    ],
)
def test_nothing_is_saved_when_toast_does_not_accept_the_connection(
    client: TestClient,
    owner: FakeDatabase,
    toast: FakeToast,
    path: str,
    reply: httpx2.Response | Exception,
    status_code: int,
) -> None:
    toast.reply(path, reply)

    response = client.put(CONNECTION, json=BODY)

    assert response.status_code == status_code
    assert SECRET not in response.text
    assert owner.pos_queries == []
    owner.session.commit.assert_not_called()


def test_database_errors_roll_back_and_return_a_safe_500(
    client: TestClient, owner: FakeDatabase
) -> None:
    owner.session.commit.side_effect = SQLAlchemyError(SECRET)

    response = client.put(CONNECTION, json=BODY)

    assert response.status_code == 500
    assert SECRET not in response.text
    owner.session.rollback.assert_called_once()


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_reading_or_disconnecting_returns_a_safe_500_when_the_database_fails(
    client: TestClient, owner: FakeDatabase, method: str
) -> None:
    owner.pos_error = SQLAlchemyError(SECRET)

    response = client.request(method, CONNECTION)

    assert response.status_code == 500
    assert SECRET not in response.text
    owner.session.rollback.assert_called_once()
    owner.session.commit.assert_not_called()


def test_get_returns_the_connected_restaurant_or_404(
    client: TestClient, owner: FakeDatabase
) -> None:
    assert client.get(CONNECTION).status_code == 404

    owner.connection = {"location_id": "guid-1", "location_name": "Mykonos Grill - Boca NEW"}
    response = client.get(CONNECTION)

    assert response.status_code == 200
    assert response.json()["location_name"] == "Mykonos Grill - Boca NEW"
    lookups = owner.queries("SELECT location_id, location_name FROM pos_connections")
    assert lookups == [{"restaurant_id": owner.user.restaurant_id, "provider": "TOAST"}] * 2


def test_disconnect_removes_the_guid_and_the_saved_credentials(
    client: TestClient, owner: FakeDatabase
) -> None:
    response = client.delete(CONNECTION)

    assert response.status_code == 200
    assert owner.queries("DELETE FROM pos_connections") == [
        {"restaurant_id": owner.user.restaurant_id, "provider": "TOAST"}
    ]
    assert owner.queries("DELETE FROM pos_credentials") == [{"pos_name": "TOAST"}]
    owner.session.commit.assert_called_once()


def test_disconnect_keeps_the_credentials_while_another_restaurant_uses_them(
    client: TestClient, owner: FakeDatabase
) -> None:
    owner.others_connected = True

    response = client.delete(CONNECTION)

    assert response.status_code == 200
    assert owner.queries("DELETE FROM pos_connections") == [
        {"restaurant_id": owner.user.restaurant_id, "provider": "TOAST"}
    ]
    assert owner.queries("DELETE FROM pos_credentials") == []
    owner.session.commit.assert_called_once()


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_kitchen_managers_and_signed_out_users_cannot_manage_the_connection(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    toast: FakeToast,
    method: str,
) -> None:
    body = BODY if method == "PUT" else None
    assert client.request(method, CONNECTION, json=body).status_code == 401

    db = sign_in(app, client, settings, monkeypatch, toast, "kitchen_manager")
    response = client.request(method, CONNECTION, json=body)
    app.dependency_overrides.clear()

    assert response.status_code == 403
    assert db.pos_queries == []
    assert toast.requests == []


@pytest.mark.parametrize("body", [{}, {"client_id": "", "client_secret": SECRET}])
def test_missing_credentials_are_rejected_before_calling_toast(
    client: TestClient, owner: FakeDatabase, toast: FakeToast, body: dict[str, str]
) -> None:
    assert client.put(CONNECTION, json=body).status_code == 422
    assert toast.requests == []
