# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Translation of Toast stock API responses into StockItem models."""

from decimal import Decimal

import httpx2
import pytest

from app.integrations.pos.models import StockItem
from app.integrations.pos.toast.client import ToastApiError
from app.integrations.pos.toast.stock import STOCK_PATH
from tests.unit.toast_fakes import CONNECTION, FIXTURES_DIR, FakeToast


@pytest.fixture
def toast() -> FakeToast:
    fake = FakeToast()
    fake.reply(STOCK_PATH, httpx2.Response(200, text=(FIXTURES_DIR / "stock.json").read_text()))
    return fake


@pytest.fixture
def items(toast: FakeToast) -> dict[str, StockItem]:
    return {item.item_id: item for item in toast.adapter().fetch_stock_items()}


def test_requests_all_limited_and_out_of_stock_items(toast: FakeToast) -> None:
    toast.adapter().fetch_stock_items()

    [request] = toast.requests_to(STOCK_PATH)
    assert request.method == "GET"
    assert not request.url.params


def test_limited_item_keeps_remaining_quantity(items: dict[str, StockItem]) -> None:
    gyro = items["item-gyro"]

    assert gyro.quantity == Decimal("12.0")
    assert gyro.is_available is True
    assert gyro.connection_id == CONNECTION.id
    assert gyro.restaurant_id == CONNECTION.restaurant_id


def test_out_of_stock_item_is_unavailable(items: dict[str, StockItem]) -> None:
    baklava = items["item-baklava"]

    assert baklava.is_available is False
    assert baklava.quantity is None


def test_modifier_options_are_included(items: dict[str, StockItem]) -> None:
    assert items["option-feta"].quantity == Decimal("0.5")


def test_names_are_not_provided_by_toast(items: dict[str, StockItem]) -> None:
    assert all(item.item_name is None for item in items.values())


def test_skips_invalid_items(items: dict[str, StockItem]) -> None:
    assert "item-unknown" not in items


@pytest.mark.parametrize(
    ("status", "available"),
    [("IN_STOCK", True), ("SOMETHING_NEW", None)],
)
def test_maps_other_statuses(toast: FakeToast, status: str, available: bool | None) -> None:
    toast.reply(
        STOCK_PATH,
        httpx2.Response(200, json=[{"guid": "item-1", "status": status, "quantity": None}]),
    )

    [item] = toast.adapter().fetch_stock_items()

    assert item.is_available is available
    assert item.quantity is None


def test_empty_response_means_everything_is_in_stock(toast: FakeToast) -> None:
    toast.reply(STOCK_PATH, httpx2.Response(200, json=[]))

    assert toast.adapter().fetch_stock_items() == []


def test_rejects_unexpected_response_shape(toast: FakeToast) -> None:
    toast.reply(STOCK_PATH, httpx2.Response(200, json={}))

    with pytest.raises(ToastApiError, match="not a JSON array"):
        toast.adapter().fetch_stock_items()
