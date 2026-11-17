# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Turns the POS models that adapters return into the rows the sales import saves.

Each row type lists every column it fills, so only those fields are ever saved: this is the
allow-list. Adapters have already dropped everything personal from the provider's data.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.integrations.pos.models import MenuItem, SaleLine, SaleModifier


@dataclass(frozen=True)
class LineRow:
    pos_line_id: str
    pos_item_id: str
    item_name: str
    quantity: Decimal
    price: Decimal | None
    modifiers: tuple[SaleModifier, ...]
    is_voided: bool


@dataclass(frozen=True)
class OrderRow:
    pos_order_id: str
    business_date: date
    opened_at: datetime
    is_mock: bool
    lines: tuple[LineRow, ...]


@dataclass(frozen=True)
class MenuItemRow:
    pos_item_id: str
    name: str
    price: Decimal | None
    currency: str
    is_mock: bool


@dataclass(frozen=True)
class ModifierRow:
    pos_modifier_id: str
    name: str
    group_name: str
    price: Decimal | None
    is_mock: bool


@dataclass(frozen=True)
class MenuRows:
    items: list[MenuItemRow]
    modifiers: list[ModifierRow]


def order_rows(lines: Sequence[SaleLine], restaurant_id: UUID) -> list[OrderRow]:
    """Group sale lines into their orders, keeping the order they came in."""
    lines_by_order: dict[str, list[SaleLine]] = {}
    for line in lines:
        _check_restaurant(line.restaurant_id, restaurant_id)
        lines_by_order.setdefault(line.order_id, []).append(line)
    return [_order_row(order_lines) for order_lines in lines_by_order.values()]


def menu_rows(items: Sequence[MenuItem], restaurant_id: UUID) -> MenuRows:
    """One row per menu item and one per modifier option. An option offered in several
    groups keeps the name of the first group it appears in."""
    item_rows: dict[str, MenuItemRow] = {}
    modifier_rows: dict[str, ModifierRow] = {}
    for item in items:
        _check_restaurant(item.restaurant_id, restaurant_id)
        item_rows.setdefault(
            item.item_id,
            MenuItemRow(
                pos_item_id=item.item_id,
                name=item.item_name,
                price=item.price,
                currency=item.currency,
                is_mock=item.is_mock,
            ),
        )
        for group in item.modifier_groups:
            for option in group.options:
                modifier_rows.setdefault(
                    option.option_id,
                    ModifierRow(
                        pos_modifier_id=option.option_id,
                        name=option.option_name,
                        group_name=group.group_name,
                        price=option.price,
                        is_mock=item.is_mock,
                    ),
                )
    return MenuRows(items=list(item_rows.values()), modifiers=list(modifier_rows.values()))


def _order_row(lines: list[SaleLine]) -> OrderRow:
    first = lines[0]
    # Keyed by line ID, so a line sent twice is saved once (the last copy wins).
    line_rows = {line.line_id: _line_row(line) for line in lines}
    return OrderRow(
        pos_order_id=first.order_id,
        business_date=first.business_date,
        opened_at=first.timestamp,
        is_mock=first.is_mock,
        lines=tuple(line_rows.values()),
    )


def _line_row(line: SaleLine) -> LineRow:
    return LineRow(
        pos_line_id=line.line_id,
        pos_item_id=line.item_id,
        item_name=line.item_name,
        quantity=line.quantity,
        price=line.price,
        modifiers=line.modifiers,
        is_voided=line.is_voided,
    )


def _check_restaurant(actual: UUID, expected: UUID) -> None:
    if actual != expected:
        raise ValueError("POS data belongs to a different restaurant than the import.")
