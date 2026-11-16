# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Toast endpoint tests with real owner sessions and restaurant connections."""

from collections.abc import Callable
from datetime import UTC, datetime, tzinfo
from typing import Any, Self
from uuid import uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.api import toast as toast_api
from app.integrations.pos.models import PosConnection
from app.integrations.pos.toast.adapter import ToastAdapter
from app.integrations.pos.toast.client import ToastCredentials
from app.integrations.pos.toast.orders import ORDERS_PATH
from app.modules.pos import service
from tests.unit.toast_fakes import BASE_URL, FakeToast


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        return cls(2026, 10, 10, 12, tzinfo=UTC)


def test_owner_connection_and_sales(
    make_client: Callable[[], TestClient],
    sign_up_owner: Callable[[TestClient, str], dict[str, Any]],
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client()
    owner = sign_up_owner(client, "owner@example.com")
    other = sign_up_owner(make_client(), "other@example.com")
    monkeypatch.setattr(
        service,
        "get_credentials",
        lambda db, provider: {"client_id": "test-client", "client_secret": "test-secret"},
    )
    with migrated_engine.begin() as db:
        db.execute(
            text("""
                INSERT INTO pos_connections (id, restaurant_id, provider, location_id)
                VALUES (:id, :restaurant_id, 'TOAST', 'restaurant-guid-1')
            """),
            {"id": uuid4(), "restaurant_id": other["restaurant_id"]},
        )

    response = client.get("/api/pos/toast/sales-summary?days=1")
    assert response.status_code == 404
    assert response.json()["detail"] == "Toast connection not configured for this restaurant."

    with migrated_engine.begin() as db:
        db.execute(
            text("""
                INSERT INTO pos_connections (id, restaurant_id, provider, location_id)
                VALUES (:id, :restaurant_id, 'TOAST', 'restaurant-guid-1')
            """),
            {"id": uuid4(), "restaurant_id": owner["restaurant_id"]},
        )

    fake = FakeToast()
    fake.reply(
        ORDERS_PATH,
        httpx2.Response(
            200,
            json=[
                {
                    "guid": "order",
                    "openedDate": "2026-10-10T12:00:00.000+0000",
                    "businessDate": 20261010,
                    "checks": [
                        {
                            "guid": "check",
                            "selections": [
                                {
                                    "guid": "sale",
                                    "item": {"guid": "item"},
                                    "quantity": 2,
                                    "price": 20,
                                },
                                {
                                    "guid": "void",
                                    "item": {"guid": "item"},
                                    "quantity": 1,
                                    "price": 7,
                                    "voided": True,
                                },
                            ],
                        }
                    ],
                }
            ],
        ),
    )

    def adapter(
        connection: PosConnection, credentials: ToastCredentials, *, currency: str, base_url: str
    ) -> ToastAdapter:
        return ToastAdapter(
            connection,
            credentials,
            currency=currency,
            base_url=BASE_URL,
            transport=httpx2.MockTransport(fake._handle),
            sleep=fake.sleep,
            clock=fake.clock,
        )

    monkeypatch.setattr(toast_api, "ToastAdapter", adapter)
    monkeypatch.setattr(toast_api, "datetime", FrozenDateTime)
    response = client.get("/api/pos/toast/sales-summary?days=1")
    assert response.status_code == 200
    assert response.json()["total_orders"] == 1
    assert response.json()["total_items"] == "2"
    assert response.json()["total_revenue"] == "20"
    assert len(fake.requests_to(ORDERS_PATH)) == 1
