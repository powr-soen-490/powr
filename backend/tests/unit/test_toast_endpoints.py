# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Toast endpoint tests with signed owner sessions and a fake Toast server."""

import importlib.util
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, tzinfo
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
from app.integrations.pos.toast.token_store import MemoryTokenStore, ToastTokenStore
from app.modules.pos import repository, service
from app.modules.pos.sales_repository import DailySales
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
def saved_login() -> dict[str, Any]:
    """What service.get_credentials returns: the decrypted pos_credentials row."""
    return {
        "client_id": "test-client",
        "client_secret": "test-secret",
        "access_token": None,
        "expires_at": None,
        "needs_reconnect": False,
    }


@pytest.fixture
def owner_client(
    app: FastAPI,
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    toast: FakeToast,
    saved_login: dict[str, Any],
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
    monkeypatch.setattr(service, "get_credentials", lambda db, provider: dict(saved_login))

    def adapter(
        db: Session, connection: PosConnection, credentials: dict[str, Any], *, currency: str
    ) -> ToastAdapter:
        return ToastAdapter(
            connection,
            ToastCredentials(
                client_id=credentials["client_id"], client_secret=credentials["client_secret"]
            ),
            currency=currency,
            base_url=BASE_URL,
            transport=httpx2.MockTransport(toast._handle),
            sleep=toast.sleep,
            clock=toast.clock,
        )

    monkeypatch.setattr(toast_api, "saved_toast_adapter", adapter)
    monkeypatch.setattr(toast_api, "datetime", FrozenDateTime)
    yield client
    app.dependency_overrides.pop(get_db, None)


def no_sales(
    db: Session, *, restaurant_id: UUID, start_date: date, end_date: date
) -> service.SalesSummary:
    return service.SalesSummary(
        daily=[], total_orders=0, total_items=Decimal("0"), total_revenue=Decimal("0")
    )


def test_sales_summary_reads_imported_sales_without_calling_toast(
    owner_client: TestClient, toast: FakeToast, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[tuple[date, date]] = []

    def imported_sales(
        db: Session, *, restaurant_id: UUID, start_date: date, end_date: date
    ) -> service.SalesSummary:
        asked.append((start_date, end_date))
        day = DailySales(date(2026, 10, 10), 2, Decimal("1.55"), Decimal("9.00"))
        return service.SalesSummary(
            daily=[day], total_orders=2, total_items=Decimal("1.55"), total_revenue=Decimal("9")
        )

    monkeypatch.setattr(service, "get_sales_summary", imported_sales)
    response = owner_client.get(f"{SALES}?days=1")

    assert response.status_code == 200
    assert response.json() == {
        "days": 1,
        "start_date": "2026-10-09",
        "end_date": "2026-10-10",
        "total_orders": 2,
        "total_items": "1.55",
        "total_revenue": "9",
        "daily_stats": [{"date": "2026-10-10", "orders": 2, "items": "1.55", "revenue": "9.00"}],
    }
    assert asked == [(date(2026, 10, 9), date(2026, 10, 10))]
    assert not toast.requests


def test_sales_summary_database_error_returns_safe_500(
    owner_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(db: Session, **_: object) -> service.SalesSummary:
        raise SQLAlchemyError("private database detail")

    monkeypatch.setattr(service, "get_sales_summary", fail)
    response = owner_client.get(SALES)

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to read imported sales."


@pytest.mark.parametrize("days", [0, -5, 366, 999])
def test_invalid_days_are_rejected_for_owner(owner_client: TestClient, days: int) -> None:
    assert owner_client.get(f"{SALES}?days={days}").status_code == 422


@pytest.mark.parametrize(("query", "days"), [("", 30), ("?days=1", 1), ("?days=365", 365)])
def test_valid_days_for_owner(
    owner_client: TestClient, monkeypatch: pytest.MonkeyPatch, query: str, days: int
) -> None:
    monkeypatch.setattr(service, "get_sales_summary", no_sales)
    response = owner_client.get(f"{SALES}{query}")
    assert response.status_code == 200
    assert response.json()["days"] == days


def test_menu_without_a_connection_returns_404(
    owner_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "get_connection", lambda db, restaurant_id, provider: None)
    response = owner_client.get(MENU)
    assert response.status_code == 404
    assert response.json()["detail"] == "Toast connection not configured for this restaurant."


def test_connection_database_error_returns_safe_500(
    owner_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(db: Session, restaurant_id: UUID, provider: str) -> None:
        raise SQLAlchemyError("private database detail")

    monkeypatch.setattr(repository, "get_connection", fail)
    response = owner_client.get(MENU)
    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to retrieve Toast connection."


def test_rejected_toast_credentials_return_502(owner_client: TestClient, toast: FakeToast) -> None:
    toast.reply(LOGIN_PATH, httpx2.Response(401))
    response = owner_client.get(MENU)
    assert response.status_code == 502
    assert response.json()["detail"] == "Toast rejected the saved login. Reconnect Toast."
    assert len(toast.requests_to(LOGIN_PATH)) == 1
    assert not toast.requests_to(ORDERS_PATH)
    assert not toast.requests_to(MENUS_PATH)


def test_a_login_already_rejected_is_not_tried_again(
    owner_client: TestClient, toast: FakeToast, saved_login: dict[str, Any]
) -> None:
    saved_login["needs_reconnect"] = True

    response = owner_client.get(MENU)

    assert response.status_code == 502
    assert response.json()["detail"] == "Toast rejected the saved login. Reconnect Toast."
    assert toast.requests == []


def test_a_rate_limited_login_returns_429(owner_client: TestClient, toast: FakeToast) -> None:
    toast.reply(LOGIN_PATH, httpx2.Response(429))

    response = owner_client.get(MENU)

    assert response.status_code == 429
    assert "few minutes" in response.json()["detail"]
    assert len(toast.requests_to(LOGIN_PATH)) == 1


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
        connection: PosConnection,
        credentials: ToastCredentials,
        *,
        currency: str,
        base_url: str,
        token_store: ToastTokenStore,
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
            token_store=token_store,
        )

    @contextmanager
    def no_saved_login(client_id: str) -> Iterator[ToastTokenStore]:
        # Like a laptop where the app was never connected to Toast with this client ID.
        assert client_id == "test-client"
        yield MemoryTokenStore()

    monkeypatch.setattr(script, "ToastAdapter", adapter)
    monkeypatch.setattr(script, "script_token_store", no_saved_login)
    script.main()
    output = capsys.readouterr().out
    assert "logging in once" in output
    assert "Total Orders: 1" in output
    assert "Total Items: 2.35" in output
    assert "Total Revenue: $20.00" in output
    assert "2026-09-09" not in output
