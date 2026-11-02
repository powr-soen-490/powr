# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Validation rules of the provider-independent POS models."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.integrations.pos.models import (
    MenuItem,
    MenuModifierGroup,
    MenuModifierOption,
    SaleLine,
    SaleModifier,
    StockItem,
)

CONNECTION_ID = uuid4()
RESTAURANT_ID = uuid4()


def make_menu_item(**overrides: Any) -> MenuItem:
    fields: dict[str, Any] = {
        "connection_id": CONNECTION_ID,
        "restaurant_id": RESTAURANT_ID,
        "item_id": "item-1",
        "item_name": "Gyro plate",
        "price": Decimal("18.50"),
        "currency": "CAD",
    }
    fields.update(overrides)
    return MenuItem(**fields)


def make_sale_line(**overrides: Any) -> SaleLine:
    fields: dict[str, Any] = {
        "connection_id": CONNECTION_ID,
        "restaurant_id": RESTAURANT_ID,
        "order_id": "order-1",
        "line_id": "line-1",
        "item_id": "item-1",
        "item_name": "Gyro plate",
        "quantity": Decimal("1"),
        "timestamp": datetime(2026, 10, 1, 18, 30, tzinfo=UTC),
    }
    fields.update(overrides)
    return SaleLine(**fields)


class TestMenuItem:
    @pytest.mark.parametrize("price", [Decimal("0"), None])
    def test_accepts_free_or_unpriced_items(self, price: Decimal | None) -> None:
        assert make_menu_item(price=price).price == price

    def test_rejects_negative_price(self) -> None:
        with pytest.raises(ValidationError):
            make_menu_item(price=Decimal("-1"))

    def test_has_no_modifier_groups_by_default(self) -> None:
        assert make_menu_item().modifier_groups == ()

    def test_keeps_modifier_groups_and_options(self) -> None:
        group = MenuModifierGroup(
            group_id="group-1",
            group_name="Toppings",
            min_selections=0,
            max_selections=2,
            options=(
                MenuModifierOption(
                    option_id="opt-1", option_name="Extra feta", price=Decimal("1.50")
                ),
            ),
        )

        item = make_menu_item(modifier_groups=(group,))

        assert item.modifier_groups[0].options[0].option_name == "Extra feta"


class TestMenuModifierGroup:
    def test_defaults_allow_any_number_of_options(self) -> None:
        group = MenuModifierGroup(group_id="group-1", group_name="Sauces")

        assert group.min_selections == 0
        assert group.max_selections is None
        assert group.options == ()

    def test_rejects_negative_selection_limits(self) -> None:
        with pytest.raises(ValidationError):
            MenuModifierGroup(group_id="group-1", group_name="Sauces", min_selections=-1)

    def test_option_price_can_be_unknown(self) -> None:
        option = MenuModifierOption(option_id="opt-1", option_name="Large")

        assert option.price is None


class TestSaleLine:
    def test_existing_fields_alone_are_still_valid(self) -> None:
        line = make_sale_line()

        assert line.price is None
        assert line.modifiers == ()

    def test_keeps_price_and_modifiers(self) -> None:
        modifier = SaleModifier(item_id="mod-1", item_name="Extra feta", quantity=Decimal("2"))

        line = make_sale_line(price=Decimal("21.50"), modifiers=(modifier,))

        assert line.price == Decimal("21.50")
        assert line.modifiers == (modifier,)

    def test_rejects_negative_price(self) -> None:
        with pytest.raises(ValidationError):
            make_sale_line(price=Decimal("-0.01"))

    def test_rejects_modifier_without_positive_quantity(self) -> None:
        with pytest.raises(ValidationError):
            SaleModifier(item_id="mod-1", item_name="Extra feta", quantity=Decimal("0"))

    def test_normalizes_timestamp_to_utc(self) -> None:
        montreal = timezone(timedelta(hours=-4))

        line = make_sale_line(timestamp=datetime(2026, 10, 1, 14, 30, tzinfo=montreal))

        assert line.timestamp == datetime(2026, 10, 1, 18, 30, tzinfo=UTC)
        assert line.timestamp.tzinfo == UTC

    def test_modifiers_cannot_be_changed_after_creation(self) -> None:
        line = make_sale_line()

        with pytest.raises(ValidationError):
            line.modifiers = ()  # type: ignore[misc]
        assert not hasattr(line.modifiers, "append")


class TestStockItem:
    def test_name_is_optional(self) -> None:
        item = StockItem(
            connection_id=CONNECTION_ID,
            restaurant_id=RESTAURANT_ID,
            item_id="item-1",
            quantity=Decimal("4"),
            is_available=True,
        )

        assert item.item_name is None

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValidationError):
            StockItem(
                connection_id=CONNECTION_ID,
                restaurant_id=RESTAURANT_ID,
                item_id="item-1",
                item_name="",
            )
            