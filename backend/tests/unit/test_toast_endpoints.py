# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Toast endpoint tests with signed owner sessions and a fake Toast server."""

import importlib.util
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, tzinfo
from decimal import Decimal
from pathlib import Path
from typing import Any, Self
from unittest.mock import Mock
from uuid import UUID, uuid4

import dotenv
import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import toast as toast_api
from app.core.auth import CurrentUser
from app.core.config import Settings
from app.core.database import get_db
from app.core.security import create_session_token
from app.integrations.pos.models import PosConnection
from app.integrations.pos.toast.adapter import ToastAdapter
from app.integrations.pos.toast.client import LOGIN_PATH, ToastCredentials
from app.integrations.pos.toast.menus import MENUS_PATH
from app.integrations.pos.toast.orders import ORDERS_PATH
from app.modules.pos import repository, service
from tests.unit.toast_fakes import BASE_URL, FakeToast, load_fixture

SALES = "/api/pos/toast/sales-summary"
MENU = "/api/pos/toast/menu"


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        return cls(2026, 10, 10, 12, tzinfo=UTC)


@pytest.fixture
def toast() -> FakeToast:
    fake = FakeToast()
    fake.reply(MENUS_PATH, httpx2.Response(200, json=load_fixture("menus.json")))
    return fake


@pytest.fixture
def owner_client(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    toast: FakeToast,
) -> Iterator[TestClient]:
    user = CurrentUser(uuid4(), "owner@example.com", uuid4(), "Restaurant", "owner")
    connection = PosConnection(
        id=uuid4(),
        restaurant_id=user.restaurant_id,
        provider="TOAST",
        location_id="restaurant-guid-1",
    )
    db = Mock(spec=Session)

    def execute(query: Any, params: dict[str, Any]) -> Mock:
        result = Mock()
        if "restaurant_memberships" in str(query):
            result.first.return_value = user
        elif "pos_connections" in str(query):
            assert params == {"restaurant_id": user.restaurant_id, "provider": "TOAST"}
            result.first.return_value = (
                connection.id,
                connection.restaurant_id,
                connection.provider,
                connection.location_id,
            )
        else:
            raise AssertionError(f"Unexpected query: {query}")
        return result

    db.execute.side_effect = execute
    app.dependency_overrides[get_db] = lambda: db
    client.cookies.set(
        settings.session_cookie_name,
        create_session_token(
            str(user.user_id),
            str(user.restaurant_id),
            role="owner",
            secret_key=settings.session_secret_key,
        ),
    )
    monkeypatch.setattr(
        service,
        "get_credentials",
        lambda db, provider: {"client_id": "test-client", "client_secret": "test-secret"},
    )

    def adapter(
        connection: PosConnection, credentials: ToastCredentials, *, currency: str, base_url: str
    ) -> ToastAdapter:
        return ToastAdapter(
            connection,
            credentials,
            currency=currency,
            base_url=BASE_URL,
            transport=httpx2.MockTransport(toast._handle),
            sleep=toast.sleep,
            clock=toast.clock,
        )

    monkeypatch.setattr(toast_api, "ToastAdapter", adapter)
    monkeypatch.setattr(toast_api, "datetime", FrozenDateTime)
    yield client
    app.dependency_overrides.pop(get_db, None)


def order(order_id: str, business_date: int, selections: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "guid": order_id,
        "openedDate": "2026-10-10T12:00:00.000+0000",
        "businessDate": business_date,
        "checks": [{"guid": f"check-{order_id}", "selections": selections}],
    }


def selection(line_id: str, quantity: int, price: int, *, voided: bool = False) -> dict[str, Any]:
    return {
        "guid": line_id,
        "item": {"guid": f"item-{line_id}"},
        "displayName": line_id,
        "quantity": quantity,
        "price": price,
        "voided": voided,
    }


def test_sales_totals_exclude_voids_and_out_of_range_dates(
    owner_client: TestClient, toast: FakeToast
) -> None:
    toast.reply(
        ORDERS_PATH,
        httpx2.Response(
            200,
            json=[
                order(
                    "one",
                    20261009,
                    [
                        selection("a", 2, 20),
                        selection("b", 1, 5),
                        selection("void", 1, 7, voided=True),
                    ],
                ),
                order("two", 20261010, [selection("c", 3, 30)]),
                order("old", 20261008, [selection("old", 1, 99)]),
                order("future", 20261011, [selection("future", 1, 99)]),
            ],
        ),
    )
    response = owner_client.get(f"{SALES}?days=1")
    assert response.status_code == 200
    body = response.json()
    assert (body["start_date"], body["end_date"]) == ("2026-10-09", "2026-10-10")
    assert (body["total_orders"], body["total_items"]) == (2, "6")
    assert Decimal(body["total_revenue"]) == Decimal("55")
    assert [
        (day["date"], day["orders"], Decimal(day["items"]), Decimal(day["revenue"]))
        for day in body["daily_stats"]
    ] == [
        ("2026-10-09", 1, Decimal("3"), Decimal("25")),
        ("2026-10-10", 1, Decimal("3"), Decimal("30")),
    ]
    assert len(toast.requests_to(ORDERS_PATH)) == 1


def test_fractional_item_quantities_are_preserved(
    owner_client: TestClient, toast: FakeToast
) -> None:
    toast.reply(
        ORDERS_PATH,
        httpx2.Response(
            200,
            text="""[{
                "guid": "order",
                "openedDate": "2026-10-10T12:00:00.000+0000",
                "businessDate": 20261010,
                "checks": [{"guid": "check", "selections": [
                    {"guid": "a", "item": {"guid": "item-a"}, "quantity": 0.35, "price": 4},
                    {"guid": "b", "item": {"guid": "item-b"}, "quantity": 1.20, "price": 5}
                ]}]
            }]""",
        ),
    )
    response = owner_client.get(f"{SALES}?days=1")
    assert response.status_code == 200
    body = response.json()
    assert body["total_items"] == "1.55"
    assert body["daily_stats"][0]["items"] == "1.55"


@pytest.mark.parametrize("days", [0, -5, 366, 999])
def test_invalid_days_are_rejected_for_owner(owner_client: TestClient, days: int) -> None:
    assert owner_client.get(f"{SALES}?days={days}").status_code == 422


@pytest.mark.parametrize(("query", "days"), [("", 30), ("?days=1", 1), ("?days=365", 365)])
def test_valid_days_for_owner(
    owner_client: TestClient, toast: FakeToast, query: str, days: int
) -> None:
    toast.reply(ORDERS_PATH, httpx2.Response(200, json=[]))
    response = owner_client.get(f"{SALES}{query}")
    assert response.status_code == 200
    assert response.json()["days"] == days


@pytest.mark.parametrize("path", [SALES, MENU])
def test_missing_connection_returns_404(
    owner_client: TestClient, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    monkeypatch.setattr(service, "get_connection", lambda db, restaurant_id, provider: None)
    response = owner_client.get(path)
    assert response.status_code == 404
    assert response.json()["detail"] == "Toast connection not configured for this restaurant."


def test_connection_database_error_returns_safe_500(
    owner_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(db: Session, restaurant_id: UUID, provider: str) -> None:
        raise SQLAlchemyError("private database detail")

    monkeypatch.setattr(repository, "get_connection", fail)
    response = owner_client.get(SALES)
    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to retrieve Toast connection."


@pytest.mark.parametrize("path", [SALES, MENU])
def test_rejected_toast_credentials_return_502(
    owner_client: TestClient, toast: FakeToast, path: str
) -> None:
    toast.reply(LOGIN_PATH, httpx2.Response(401))
    response = owner_client.get(path)
    assert response.status_code == 502
    assert response.json()["detail"] == "Toast authentication failed. Check credentials."
    assert len(toast.requests_to(LOGIN_PATH)) == 1
    assert not toast.requests_to(ORDERS_PATH)
    assert not toast.requests_to(MENUS_PATH)


def test_menu_uses_usd_and_includes_modifiers(owner_client: TestClient, toast: FakeToast) -> None:
    response = owner_client.get(MENU)
    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "USD"
    gyro = next(item for item in body["items"] if item["item_id"] == "item-gyro")
    assert gyro["currency"] == "USD"
    assert gyro["modifier_groups"][0]["options"][0]["option_id"] == "option-feta"
    assert len(toast.requests_to(MENUS_PATH)) == 1


@pytest.mark.parametrize("path", [SALES, MENU])
def test_requires_authentication(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 401


def test_pull_script_filters_sales_and_uses_usd(
    toast: FakeToast, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = Path(__file__).resolve().parents[3] / "scripts" / "pull_toast_sales.py"
    spec = importlib.util.spec_from_file_location("pull_toast_sales_test", path)
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    spec.loader.exec_module(script)
    toast.reply(
        ORDERS_PATH,
        httpx2.Response(
            200,
            text="""[
            {"guid":"sale","openedDate":"2026-10-10T12:00:00.000+0000","businessDate":20261009,
             "checks":[{"guid":"check","selections":[
                 {"guid":"sale","item":{"guid":"item"},"quantity":2.35,"price":20},
                 {"guid":"void","item":{"guid":"item"},"quantity":1,"price":7,"voided":true}
             ]}]},
            {"guid":"old","openedDate":"2026-10-10T12:00:00.000+0000","businessDate":20260909,
             "checks":[{"guid":"old-check","selections":[
                 {"guid":"old","item":{"guid":"item"},"quantity":1,"price":99}
             ]}]}
        ]""",
        ),
        httpx2.Response(200, json=[]),
    )
    settings = Mock(
        toast_client_id="test-client",
        toast_client_secret="test-secret",
        toast_restaurant_guid="restaurant-guid-1",
        toast_api_base_url=BASE_URL,
    )
    monkeypatch.setattr(script, "get_settings", lambda: settings)
    monkeypatch.setattr(script, "datetime", FrozenDateTime)

    def adapter(
        connection: PosConnection, credentials: ToastCredentials, *, currency: str, base_url: str
    ) -> ToastAdapter:
        assert currency == "USD"
        return ToastAdapter(
            connection,
            credentials,
            currency=currency,
            base_url=base_url,
            transport=httpx2.MockTransport(toast._handle),
            sleep=toast.sleep,
            clock=toast.clock,
        )

    monkeypatch.setattr(script, "ToastAdapter", adapter)
    script.main()
    output = capsys.readouterr().out
    assert "Total Orders: 1" in output
    assert "Total Items: 2.35" in output
    assert "Total Revenue: $20.00" in output
    assert "2026-09-09" not in output
