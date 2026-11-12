# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Translation of Toast menus v2 responses into MenuItem models."""

import json
from decimal import Decimal

import httpx2
import pytest

from app.integrations.pos.models import MenuItem
from app.integrations.pos.toast.client import ToastApiError
from app.integrations.pos.toast.menus import MENUS_PATH
from tests.unit.toast_fakes import CONNECTION, FIXTURES_DIR, FakeToast


@pytest.fixture
def toast() -> FakeToast:
    fake = FakeToast()
    # Served as raw text so the adapter parses it exactly like a real Toast response.
    fake.reply(MENUS_PATH, httpx2.Response(200, text=(FIXTURES_DIR / "menus.json").read_text()))
    return fake


@pytest.fixture
def items(toast: FakeToast) -> dict[str, MenuItem]:
    return {item.item_id: item for item in toast.adapter().fetch_menu_items()}


def test_requests_menus_v2(toast: FakeToast) -> None:
    toast.adapter().fetch_menu_items()

    assert len(toast.requests_to(MENUS_PATH)) == 1


def test_finds_items_in_every_menu_and_nested_group(items: dict[str, MenuItem]) -> None:
    assert set(items) == {"item-gyro", "item-souvlaki", "item-pizza", "item-baklava"}


def test_maps_item_fields(items: dict[str, MenuItem]) -> None:
    gyro = items["item-gyro"]

    assert gyro.item_name == "Gyro plate"
    assert gyro.connection_id == CONNECTION.id
    assert gyro.restaurant_id == CONNECTION.restaurant_id
    assert gyro.currency == "CAD"


def test_item_on_several_menus_is_returned_once_with_first_price(
    toast: FakeToast,
) -> None:
    menu_items = toast.adapter().fetch_menu_items()

    gyros = [item for item in menu_items if item.item_id == "item-gyro"]
    assert len(gyros) == 1
    assert gyros[0].price == Decimal("18.50")


def test_keeps_free_and_unpriced_items(items: dict[str, MenuItem]) -> None:
    assert items["item-souvlaki"].price == Decimal("0")
    assert items["item-pizza"].price is None


def test_replaces_empty_name(items: dict[str, MenuItem]) -> None:
    assert items["item-baklava"].item_name == "Missing name"


def test_resolves_modifier_groups_and_options(items: dict[str, MenuItem]) -> None:
    [toppings] = items["item-gyro"].modifier_groups

    assert toppings.group_id == "modgroup-toppings"
    assert toppings.group_name == "Toppings"
    assert toppings.min_selections == 0
    assert toppings.max_selections is None
    assert [(option.option_name, option.price) for option in toppings.options] == [
        ("Extra feta", Decimal("1.50")),
        ("Tzatziki", Decimal("0")),
    ]


def test_size_priced_option_has_no_price(items: dict[str, MenuItem]) -> None:
    [size] = items["item-pizza"].modifier_groups

    assert (size.min_selections, size.max_selections) == (1, 1)
    assert size.options[0].price is None


def test_item_without_modifiers_has_none(items: dict[str, MenuItem]) -> None:
    assert items["item-souvlaki"].modifier_groups == ()
    assert items["item-baklava"].modifier_groups == ()


def test_empty_menu_returns_no_items(toast: FakeToast) -> None:
    toast.reply(MENUS_PATH, httpx2.Response(200, text=json.dumps({"menus": []})))

    assert toast.adapter().fetch_menu_items() == []


def test_rejects_unexpected_response_shape(toast: FakeToast) -> None:
    toast.reply(MENUS_PATH, httpx2.Response(200, text="[]"))

    with pytest.raises(ToastApiError, match="not a JSON object"):
        toast.adapter().fetch_menu_items()
