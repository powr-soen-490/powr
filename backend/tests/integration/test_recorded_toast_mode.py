# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Local development without Toast (TOAST_USE_RECORDED_DATA): connect with any login, then
import the recorded week through the real endpoints, adapter and database."""

import base64
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core import encryption
from app.core.config import Settings
from app.integrations.pos.toast.recorded import RECORDED_RESTAURANT_NAME
from app.modules.pos import service

# Sale lines in each recorded day, Nov 9 to 15, and the orders they belong to. The week has
# 368 Toast orders, but one (Nov 15) is an empty voided order with no items, so nothing is saved.
WEEK_LINES = 110 + 125 + 113 + 117 + 94 + 91 + 93
WEEK_ORDERS = 367


@pytest.fixture(autouse=True)
def recorded_toast(monkeypatch: pytest.MonkeyPatch) -> None:
    key = SecretStr(base64.urlsafe_b64encode(bytes(range(32))).decode())
    settings = Settings(
        _env_file=None, pos_credentials_encryption_key=key, toast_use_recorded_data=True
    )
    monkeypatch.setattr(encryption, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "get_settings", lambda: settings)


def test_the_recorded_week_imports_without_toast_credentials(
    make_client: Callable[[], TestClient],
    sign_up_owner: Callable[[TestClient, str], dict[str, Any]],
) -> None:
    owner = make_client()
    sign_up_owner(owner, "owner@example.com")

    connected = owner.put(
        "/api/pos/toast/connection", json={"client_id": "anything", "client_secret": "anything"}
    )
    assert connected.status_code == 200, connected.text
    assert connected.json()["location_name"] == RECORDED_RESTAURANT_NAME

    started = owner.post(
        "/api/pos/toast/imports", json={"start_date": "2026-11-09", "end_date": "2026-11-15"}
    )
    assert started.status_code == 202, started.text

    latest = owner.get("/api/pos/toast/imports/latest").json()
    assert (latest["status"], latest["percent"], latest["error"]) == ("done", 100, None)
    assert (latest["orders_imported"], latest["items_imported"]) == (WEEK_ORDERS, WEEK_LINES)

    menu = owner.get("/api/pos/toast/menu")
    assert menu.status_code == 200, menu.text
    assert len(menu.json()["items"]) == 214
