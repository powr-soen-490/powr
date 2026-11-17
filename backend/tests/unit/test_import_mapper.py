# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Turning adapter models into the rows the sales import saves."""

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.integrations.pos.models import (
    MenuItem,
    MenuModifierGroup,
    MenuModifierOption,
    SaleLine,
    SaleModifier,
)
from app.modules.pos.import_mapper import (
    LineRow,
    MenuItemRow,
    ModifierRow,
    OrderRow,
    menu_rows,
    order_rows,
)
from tests.unit.toast_fakes import CONNECTION

NOV_9 = date(2026, 11, 9)
OPENED = datetime(2026, 11, 9, 18, 30, tzinfo=UTC)
FETA = SaleModifier(item_id="option-feta", item_name="Extra feta", quantity=Decimal("2"))


def sale_line(order_id: str, line_id: str, **changes: object) -> SaleLine:
    values: dict[str, object] = {
        "connection_id": CONNECTION.id,
        "restaurant_id": CONNECTION.restaurant_id,
        "order_id": order_id,
        "line_id": line_id,
        "item_id": "item-gyro",
        "item_name": "Gyro plate",
        "quantity": Decimal("1"),
        "timestamp": OPENED,
        "business_date": NOV_9,
        "price": Decimal("18.50"),
        "modifiers": (FETA,),
    }
    return SaleLine.model_validate(values | changes)


def menu_item(item_id: str, *groups: MenuModifierGroup) -> MenuItem:
    return MenuItem(
        connection_id=CONNECTION.id,
        restaurant_id=CONNECTION.restaurant_id,
        item_id=item_id,
        item_name=f"Item {item_id}",
        price=Decimal("12.00"),
        currency="USD",
        modifier_groups=groups,
    )


def group(name: str, *option_ids: str) -> MenuModifierGroup:
    options = tuple(
        MenuModifierOption(option_id=option_id, option_name=option_id, price=Decimal("1.00"))
        for option_id in option_ids
    )
    return MenuModifierGroup(group_id=name, group_name=name, min_selections=0, options=options)


def test_lines_are_grouped_into_their_orders() -> None:
    lines = [
        sale_line("order-1", "line-1"),
        sale_line("order-2", "line-3", quantity=Decimal("0.35"), is_voided=True),
        sale_line("order-1", "line-2"),
    ]

    orders = order_rows(lines, CONNECTION.restaurant_id)

    assert [order.pos_order_id for order in orders] == ["order-1", "order-2"]
    assert orders[0] == OrderRow(
        pos_order_id="order-1",
        business_date=NOV_9,
        opened_at=OPENED,
        is_mock=False,
        lines=(
            LineRow(
                "line-1", "item-gyro", "Gyro plate", Decimal("1"), Decimal("18.50"), (FETA,), False
            ),
            LineRow(
                "line-2", "item-gyro", "Gyro plate", Decimal("1"), Decimal("18.50"), (FETA,), False
            ),
        ),
    )
    assert orders[1].lines[0].quantity == Decimal("0.35")
    assert orders[1].lines[0].is_voided


def test_a_line_sent_twice_is_saved_once() -> None:
    lines = [sale_line("order-1", "line-1"), sale_line("order-1", "line-1", is_voided=True)]

    [order] = order_rows(lines, CONNECTION.restaurant_id)

    assert len(order.lines) == 1
    assert order.lines[0].is_voided


def test_mock_sales_stay_marked_as_mock() -> None:
    [order] = order_rows([sale_line("order-1", "line-1", is_mock=True)], CONNECTION.restaurant_id)

    assert order.is_mock


def test_data_from_another_restaurant_is_refused() -> None:
    with pytest.raises(ValueError, match="different restaurant"):
        order_rows([sale_line("order-1", "line-1")], uuid4())
    with pytest.raises(ValueError, match="different restaurant"):
        menu_rows([menu_item("item-gyro")], uuid4())


def test_modifier_options_are_flattened_and_saved_once() -> None:
    items = [
        menu_item("item-gyro", group("Add-ons", "option-feta", "option-olives")),
        menu_item("item-salad", group("Salad add-ons", "option-feta")),
        menu_item("item-gyro"),  # the same item on a second menu
    ]

    menu = menu_rows(items, CONNECTION.restaurant_id)

    assert [row.pos_item_id for row in menu.items] == ["item-gyro", "item-salad"]
    assert menu.modifiers == [
        ModifierRow("option-feta", "option-feta", "Add-ons", Decimal("1.00"), False),
        ModifierRow("option-olives", "option-olives", "Add-ons", Decimal("1.00"), False),
    ]


@pytest.mark.parametrize(
    ("row_type", "columns"),
    [
        (OrderRow, {"pos_order_id", "business_date", "opened_at", "is_mock", "lines"}),
        (
            LineRow,
            {
                "pos_line_id",
                "pos_item_id",
                "item_name",
                "quantity",
                "price",
                "modifiers",
                "is_voided",
            },
        ),
        (MenuItemRow, {"pos_item_id", "name", "price", "currency", "is_mock"}),
        (ModifierRow, {"pos_modifier_id", "name", "group_name", "price", "is_mock"}),
    ],
)
def test_rows_hold_only_allow_listed_fields(row_type: type, columns: set[str]) -> None:
    """Adding a field to a row is a deliberate change to what powr stores, so it fails here."""
    assert {field.name for field in dataclasses.fields(row_type)} == columns
