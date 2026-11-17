# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""How many times powr logs in to Toast, through the real endpoints and database (issue #173).

Toast asks for at most two logins per hour, so connecting saves the login's token and every
later request reuses it. Toast is the recorded week behind a transport that counts logins.
"""

import base64
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, text

from app.core import encryption
from app.core.config import Settings
from app.integrations.pos.toast.client import LOGIN_PATH
from app.integrations.pos.toast.recorded import recorded_toast_transport
from app.modules.pos import service

CONNECTION = "/api/pos/toast/connection"
IMPORTS = "/api/pos/toast/imports"
LOGIN = {"client_id": "client-id", "client_secret": "client-secret"}
A_DAY = {"start_date": "2026-11-09", "end_date": "2026-11-09"}


class CountingToast:
    """The recorded Toast week, counting logins; ``reject_logins`` makes Toast answer 401."""

    def __init__(self) -> None:
        self.logins = 0
        self.reject_logins = False
        self._recorded = recorded_toast_transport()

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._handle)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.path == LOGIN_PATH:
            self.logins += 1
            if self.reject_logins:
                return httpx2.Response(401)
        return self._recorded.handle_request(request)


@pytest.fixture
def toast(monkeypatch: pytest.MonkeyPatch) -> CountingToast:
    key = SecretStr(base64.urlsafe_b64encode(bytes(range(32))).decode())
    settings = Settings(_env_file=None, pos_credentials_encryption_key=key)
    monkeypatch.setattr(encryption, "get_settings", lambda: settings)
    counting = CountingToast()
    monkeypatch.setattr(service, "toast_transport", counting.transport)
    return counting


@pytest.fixture
def owner(
    make_client: Callable[[], TestClient],
    sign_up_owner: Callable[[TestClient, str], dict[str, Any]],
) -> TestClient:
    client = make_client()
    sign_up_owner(client, "owner@example.com")
    return client


def import_a_day(owner: TestClient) -> dict[str, Any]:
    assert owner.post(IMPORTS, json=A_DAY).status_code == 202
    latest: dict[str, Any] = owner.get(f"{IMPORTS}/latest").json()
    return latest


def saved_login(engine: Engine) -> dict[str, Any]:
    with engine.connect() as db:
        row = db.execute(
            text("SELECT access_token, expires_at, needs_reconnect FROM pos_credentials")
        ).mappings()
        return dict(row.one())


def expire_the_saved_token(engine: Engine) -> None:
    with engine.begin() as db:
        db.execute(
            text("UPDATE pos_credentials SET expires_at = :past"),
            {"past": datetime.now(UTC) - timedelta(minutes=1)},
        )


def test_connect_then_import_and_menu_log_in_once(
    owner: TestClient, toast: CountingToast, migrated_engine: Engine
) -> None:
    assert owner.put(CONNECTION, json=LOGIN).status_code == 200
    assert import_a_day(owner)["status"] == "done"
    assert owner.get("/api/pos/toast/menu").status_code == 200

    assert toast.logins == 1
    login = saved_login(migrated_engine)
    assert login["access_token"].startswith(encryption.ENVELOPE_PREFIX)
    assert login["expires_at"] > datetime.now(UTC)


def test_an_expired_token_costs_one_more_login_and_is_replaced(
    owner: TestClient, toast: CountingToast, migrated_engine: Engine
) -> None:
    owner.put(CONNECTION, json=LOGIN)
    expire_the_saved_token(migrated_engine)

    assert import_a_day(owner)["status"] == "done"
    assert import_a_day(owner)["status"] == "done"

    assert toast.logins == 2
    assert saved_login(migrated_engine)["expires_at"] > datetime.now(UTC)


def test_a_rejected_login_needs_a_reconnect_and_reconnecting_clears_it(
    owner: TestClient, toast: CountingToast, migrated_engine: Engine
) -> None:
    owner.put(CONNECTION, json=LOGIN)
    expire_the_saved_token(migrated_engine)
    toast.reject_logins = True

    failed = import_a_day(owner)

    assert failed["status"] == "failed"
    assert "Reconnect Toast" in failed["error"]
    assert saved_login(migrated_engine)["needs_reconnect"] is True
    assert toast.logins == 2

    # Toast already said no, so trying again does not spend another login.
    assert import_a_day(owner)["status"] == "failed"
    assert owner.get("/api/pos/toast/menu").status_code == 502
    assert toast.logins == 2

    toast.reject_logins = False
    assert owner.put(CONNECTION, json=LOGIN).status_code == 200
    assert saved_login(migrated_engine)["needs_reconnect"] is False
    assert import_a_day(owner)["status"] == "done"
    assert toast.logins == 3


def test_a_rate_limited_login_stops_the_import_without_a_reconnect(
    owner: TestClient,
    toast: CountingToast,
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner.put(CONNECTION, json=LOGIN)
    expire_the_saved_token(migrated_engine)

    def limited(request: httpx2.Request) -> httpx2.Response:
        toast.logins += 1
        return httpx2.Response(429)

    monkeypatch.setattr(service, "toast_transport", lambda: httpx2.MockTransport(limited))

    failed = import_a_day(owner)

    assert failed["status"] == "failed"
    assert "few minutes" in failed["error"]
    assert toast.logins == 2
    assert saved_login(migrated_engine)["needs_reconnect"] is False
