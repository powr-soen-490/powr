# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Scrubbing recorded Toast responses: nothing personal is kept, and nothing powr needs is lost."""

import copy
import json
from datetime import date
from decimal import Decimal
from typing import Any

import httpx2
import pytest

from app.integrations.pos.toast.client import LOGIN_PATH, ToastApiError
from app.integrations.pos.toast.menus import MENUS_PATH, menu_items_from_toast
from app.integrations.pos.toast.orders import (
    ORDERS_PAGE_SIZE,
    ORDERS_PATH,
    orders_on_business_date,
    sale_lines_from_order,
)
from app.integrations.pos.toast.recording import (
    FAKE_RESTAURANT_GUID,
    find_personal_data,
    record_days,
    scrub_menus,
    scrub_orders,
    to_json,
)
from tests.unit.toast_fakes import CONNECTION, FIXTURES_DIR, RESTAURANT_GUID, FakeToast

NOV_2 = date(2026, 11, 2)
NOV_3 = date(2026, 11, 3)
# Values that must never reach a scrubbed file.
PERSONAL_VALUES = ("Maria Papadopoulos", "maria@example.com", "561-555-0123", "4111", "Boca Raton")


def toast_json(name: str) -> Any:
    """A fixture parsed the way ToastClient parses responses, with exact decimals."""
    return json.loads((FIXTURES_DIR / name).read_text(), parse_float=Decimal)


def with_personal_data(orders: list[Any]) -> list[Any]:
    """The orders fixture plus the kinds of personal data real Toast orders carry."""
    orders = copy.deepcopy(orders)
    customer = {"firstName": "Maria Papadopoulos", "email": "maria@example.com"}
    orders[0]["server"] = {"guid": "employee-1", "firstName": "Maria Papadopoulos"}
    orders[0]["deliveryInfo"] = {"address1": "1 Main St", "city": "Boca Raton"}
    orders[0]["restaurantGuid"] = RESTAURANT_GUID
    check = orders[0]["checks"][0]
    check["customer"] = {**customer, "phone": "561-555-0123"}
    check["payments"] = [{"cardType": "VISA", "last4Digits": "4111", "amount": 40}]
    check["selections"][0]["displayName"] = {"email": "maria@example.com"}
    return orders


def test_scrubbed_orders_keep_every_sale_line() -> None:
    orders = toast_json("orders.json")

    scrubbed = scrub_orders(orders, RESTAURANT_GUID)

    def lines(source: list[Any]) -> list[Any]:
        return [line for order in source for line in sale_lines_from_order(order, CONNECTION)]

    assert lines(scrubbed) == lines(orders)


def test_scrubbed_orders_drop_personal_data() -> None:
    scrubbed = scrub_orders(with_personal_data(toast_json("orders.json")), RESTAURANT_GUID)

    saved = to_json(scrubbed)
    for value in (*PERSONAL_VALUES, RESTAURANT_GUID, "employee-1"):
        assert value not in saved
    check = scrubbed[0]["checks"][0]
    assert {"customer", "payments"}.isdisjoint(check)
    assert {"server", "deliveryInfo", "restaurantGuid"}.isdisjoint(scrubbed[0])
    # An object where a plain value belongs is dropped, not copied.
    assert check["selections"][0]["displayName"] is None


def test_scrubbed_menus_keep_every_menu_item_and_hide_the_restaurant() -> None:
    menus = toast_json("menus.json")
    menus["menus"][0]["description"] = "Call Maria at 561-555-0123"

    scrubbed = scrub_menus(menus, RESTAURANT_GUID)

    assert menu_items_from_toast(scrubbed, CONNECTION, "CAD") == menu_items_from_toast(
        menus, CONNECTION, "CAD"
    )
    assert scrubbed["restaurantGuid"] == FAKE_RESTAURANT_GUID
    saved = to_json(scrubbed)
    assert RESTAURANT_GUID not in saved
    assert "561-555-0123" not in saved
    assert "pricingStrategy" not in saved


def test_scrub_menus_rejects_a_response_that_is_not_an_object() -> None:
    with pytest.raises(ToastApiError):
        scrub_menus([], RESTAURANT_GUID)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("maria@example.com", "email address"),
        ("Card 4111 1111 1111 1111", "card number"),
        ("(561) 555-0123", "phone number"),
        ("561.555.0123", "phone number"),
    ],
)
def test_find_personal_data_flags_where_it_is(text: str, kind: str) -> None:
    assert find_personal_data({"orders": [{"displayName": text}]}) == [
        f"$.orders[0].displayName: {kind}"
    ]


def test_find_personal_data_ignores_normal_order_values() -> None:
    order = {
        "guid": "0b8e4a7c-1234-4567-8901-123456789012",
        "openedDate": "2026-11-02T18:30:00.000-0500",
        "businessDate": 20261102,
        "displayName": "Gyro plate (2 pitas)",
        "price": Decimal("18.50"),
    }

    assert find_personal_data([order]) == []


def test_orders_on_business_date_reads_every_page() -> None:
    fake = FakeToast()
    full_page = [{"guid": f"order-{n}"} for n in range(ORDERS_PAGE_SIZE)]
    fake.reply(
        ORDERS_PATH,
        httpx2.Response(200, json=full_page),
        httpx2.Response(200, json=[{"guid": "last-order"}]),
    )

    orders = list(orders_on_business_date(fake.client(), NOV_2))

    assert len(orders) == ORDERS_PAGE_SIZE + 1
    params = [request.url.params for request in fake.requests_to(ORDERS_PATH)]
    assert [p["page"] for p in params] == ["1", "2"]
    assert {p["businessDate"] for p in params} == {"20261102"}


def test_orders_on_business_date_rejects_a_response_that_is_not_a_list() -> None:
    fake = FakeToast()
    fake.reply(ORDERS_PATH, httpx2.Response(200, json={"orders": []}))

    with pytest.raises(ToastApiError):
        list(orders_on_business_date(fake.client(), NOV_2))


def test_record_days_logs_in_once_and_scrubs_each_day() -> None:
    fake = FakeToast()
    orders = with_personal_data(toast_json("orders.json"))
    fake.reply(MENUS_PATH, httpx2.Response(200, text=(FIXTURES_DIR / "menus.json").read_text()))
    fake.reply(
        ORDERS_PATH,
        httpx2.Response(200, text=to_json(orders)),
        httpx2.Response(200, json=[]),
    )

    recorded = record_days(fake.client(), NOV_2, 2, RESTAURANT_GUID)

    assert len(fake.requests_to(LOGIN_PATH)) == 1
    days = [request.url.params["businessDate"] for request in fake.requests_to(ORDERS_PATH)]
    assert days == ["20261102", "20261103"]
    assert list(recorded.files()) == [
        "menus.json",
        "orders/2026-11-02.json",
        "orders/2026-11-03.json",
    ]
    assert recorded.orders_by_day[NOV_3] == []
    assert find_personal_data(recorded.files()) == []
    assert RESTAURANT_GUID not in to_json(recorded.files())


def test_to_json_keeps_prices_and_quantities_exact() -> None:
    saved = to_json({"price": Decimal("4.20"), "quantity": Decimal("0.35"), "count": Decimal("2")})

    assert json.loads(saved, parse_float=Decimal) == {
        "price": Decimal("4.2"),
        "quantity": Decimal("0.35"),
        "count": 2,
    }
