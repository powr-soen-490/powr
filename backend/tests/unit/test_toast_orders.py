# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Fetching Toast orders by date range and translating them into SaleLine models."""

import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx2
import pytest

from app.integrations.pos.models import SaleLine, SaleModifier
from app.integrations.pos.toast import adapter as adapter_module
from app.integrations.pos.toast.client import ToastApiError
from app.integrations.pos.toast.orders import (
    ORDERS_PAGE_SIZE,
    ORDERS_PATH,
    order_windows,
    toast_datetime,
)
from tests.unit.toast_fakes import CONNECTION, FIXTURES_DIR, FakeToast

OCT_1 = datetime(2026, 10, 1, tzinfo=UTC)
OCT_2 = datetime(2026, 10, 2, tzinfo=UTC)


def orders_response(orders: list[dict[str, Any]]) -> httpx2.Response:
    return httpx2.Response(200, text=json.dumps(orders))


def simple_order(number: int) -> dict[str, Any]:
    return {
        "guid": f"order-{number}",
        "openedDate": "2026-10-01T18:00:00.000+0000",
        "checks": [
            {
                "selections": [
                    {
                        "guid": f"line-{number}",
                        "item": {"guid": "item-gyro"},
                        "displayName": "Gyro plate",
                        "quantity": 1,
                    }
                ]
            }
        ],
    }


@pytest.fixture
def toast() -> FakeToast:
    fake = FakeToast()
    fake.reply(ORDERS_PATH, httpx2.Response(200, text=(FIXTURES_DIR / "orders.json").read_text()))
    return fake


@pytest.fixture
def lines(toast: FakeToast) -> dict[str, SaleLine]:
    return {line.line_id: line for line in toast.adapter().fetch_orders(OCT_1, OCT_2)}


class TestRequests:
    def test_sends_date_range_and_first_page(self, toast: FakeToast) -> None:
        toast.adapter().fetch_orders(OCT_1, OCT_2)

        [request] = toast.requests_to(ORDERS_PATH)
        assert dict(request.url.params) == {
            "startDate": "2026-10-01T00:00:00.000+0000",
            "endDate": "2026-10-02T00:00:00.000+0000",
            "pageSize": "100",
            "page": "1",
        }

    def test_splits_long_ranges_into_weekly_windows(self, toast: FakeToast) -> None:
        toast.reply(ORDERS_PATH, orders_response([]))

        toast.adapter().fetch_orders(OCT_1, OCT_1 + timedelta(days=15))

        windows = [
            (request.url.params["startDate"], request.url.params["endDate"])
            for request in toast.requests_to(ORDERS_PATH)
        ]
        assert windows == [
            ("2026-10-01T00:00:00.000+0000", "2026-10-08T00:00:00.000+0000"),
            ("2026-10-08T00:00:00.000+0000", "2026-10-15T00:00:00.000+0000"),
            ("2026-10-15T00:00:00.000+0000", "2026-10-16T00:00:00.000+0000"),
        ]

    def test_requests_next_page_while_pages_are_full(self, toast: FakeToast) -> None:
        full_page = [simple_order(number) for number in range(ORDERS_PAGE_SIZE)]
        last_page = [simple_order(ORDERS_PAGE_SIZE)]
        toast.reply(ORDERS_PATH, orders_response(full_page), orders_response(last_page))

        lines = toast.adapter().fetch_orders(OCT_1, OCT_2)

        pages = [request.url.params["page"] for request in toast.requests_to(ORDERS_PATH)]
        assert pages == ["1", "2"]
        assert len(lines) == ORDERS_PAGE_SIZE + 1

    def test_stops_after_too_many_full_pages(
        self, toast: FakeToast, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(adapter_module, "MAX_ORDER_PAGES_PER_WINDOW", 2)
        full_page = [simple_order(number) for number in range(ORDERS_PAGE_SIZE)]
        toast.reply(ORDERS_PATH, orders_response(full_page))

        with pytest.raises(ToastApiError, match="more than 2 order pages"):
            toast.adapter().fetch_orders(OCT_1, OCT_2)

    @pytest.mark.parametrize(
        ("start", "end"),
        [(OCT_2, OCT_1), (OCT_1, OCT_1), (datetime(2026, 10, 1), OCT_2)],
    )
    def test_rejects_invalid_ranges(self, toast: FakeToast, start: datetime, end: datetime) -> None:
        with pytest.raises(ValueError):
            toast.adapter().fetch_orders(start, end)
        assert toast.requests == []

    def test_rejects_unexpected_response_shape(self, toast: FakeToast) -> None:
        toast.reply(ORDERS_PATH, httpx2.Response(200, text="{}"))

        with pytest.raises(ToastApiError, match="not a JSON array"):
            toast.adapter().fetch_orders(OCT_1, OCT_2)


class TestSaleLines:
    def test_keeps_only_sold_menu_items(self, lines: dict[str, SaleLine]) -> None:
        assert set(lines) == {"line-gyro", "line-olives", "line-refunded"}

    def test_maps_line_fields(self, lines: dict[str, SaleLine]) -> None:
        gyro = lines["line-gyro"]

        assert gyro.order_id == "order-1"
        assert gyro.item_id == "item-gyro"
        assert gyro.item_name == "Gyro plate"
        assert gyro.quantity == Decimal("2")
        assert gyro.price == Decimal("40.00")
        assert gyro.connection_id == CONNECTION.id
        assert gyro.restaurant_id == CONNECTION.restaurant_id

    def test_uses_opened_date_in_utc(self, lines: dict[str, SaleLine]) -> None:
        assert lines["line-gyro"].timestamp == datetime(2026, 10, 1, 18, 30, tzinfo=UTC)

    def test_keeps_weighed_quantities_exact(self, lines: dict[str, SaleLine]) -> None:
        assert lines["line-olives"].quantity == Decimal("0.35")

    def test_keeps_modifiers_except_voided_ones(self, lines: dict[str, SaleLine]) -> None:
        assert lines["line-gyro"].modifiers == (
            SaleModifier(item_id="option-feta", item_name="Extra feta", quantity=Decimal("2")),
        )

    def test_keeps_refunded_items(self, lines: dict[str, SaleLine]) -> None:
        assert lines["line-refunded"].item_id == "item-souvlaki"


class TestHelpers:
    def test_order_windows_cover_the_range_without_gaps(self) -> None:
        end = OCT_1 + timedelta(days=10)

        windows = list(order_windows(OCT_1, end))

        assert windows == [(OCT_1, OCT_1 + timedelta(days=7)), (OCT_1 + timedelta(days=7), end)]

    def test_toast_datetime_converts_to_utc_with_milliseconds(self) -> None:
        montreal = timezone(timedelta(hours=-4))

        value = toast_datetime(datetime(2026, 10, 1, 0, 0, 5, 123456, tzinfo=montreal))

        assert value == "2026-10-01T04:00:05.123+0000"
