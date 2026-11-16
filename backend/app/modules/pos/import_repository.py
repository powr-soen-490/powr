# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Database writes for the POS sales import: menus, and one business day of orders at a time.

Everything is an upsert (insert, or update when the row already exists), so running an import
again never saves anything twice. Rows are sent as one JSON array per statement, so a day of
orders takes a few round trips to the database instead of one per order. Nothing here
commits: the caller saves a whole day, or nothing, in one transaction.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import TextClause, text
from sqlalchemy.orm import Session

from app.modules.pos.import_mapper import LineRow, MenuRows, OrderRow


@dataclass(frozen=True)
class SavedDay:
    orders: int
    lines: int


def save_menu(db: Session, *, restaurant_id: UUID, provider: str, menu: MenuRows) -> None:
    """Upsert menu items and modifiers. Ones the POS no longer lists become inactive, never
    deleted. An empty menu changes nothing: it is far more likely an error than a real menu."""
    if not menu.items:
        return
    keys = {"restaurant_id": restaurant_id, "provider": provider}
    db.execute(_UPSERT_MENU_ITEMS, {**keys, "rows": _json(menu.items)})
    db.execute(_UPSERT_MODIFIERS, {**keys, "rows": _json(menu.modifiers)})
    # Real and generated (mock) menus never deactivate each other's rows.
    is_mock = menu.items[0].is_mock
    db.execute(
        _deactivate_missing("menu_items", "pos_item_id"),
        {**keys, "is_mock": is_mock, "ids": [row.pos_item_id for row in menu.items]},
    )
    db.execute(
        _deactivate_missing("menu_modifiers", "pos_modifier_id"),
        {**keys, "is_mock": is_mock, "ids": [row.pos_modifier_id for row in menu.modifiers]},
    )


def save_sales_day(
    db: Session, *, restaurant_id: UUID, provider: str, currency: str, orders: list[OrderRow]
) -> SavedDay:
    """Upsert one business day of orders and their lines.

    - A line that is now voided gets is_voided = true.
    - A saved line missing from its re-fetched order also gets is_voided = true.
    - A sold item that is not on the menu gets an inactive menu item, named as on its first
      sale. Toast "open items" (names typed at the till) all share one item ID, so their
      lines keep their own item_name.
    """
    if not orders:
        return SavedDay(orders=0, lines=0)
    keys = {"restaurant_id": restaurant_id, "provider": provider}
    lines = _json([_line_values(order, line) for order in orders for line in order.lines])
    db.execute(_UPSERT_ORDERS, {**keys, "rows": _json([_order_values(o) for o in orders])})
    db.execute(_UPSERT_LINES, {**keys, "rows": lines})
    db.execute(
        _VOID_MISSING_LINES,
        {**keys, "rows": lines, "order_ids": [order.pos_order_id for order in orders]},
    )
    db.execute(
        _ADD_PLACEHOLDER_ITEMS,
        {**keys, "rows": _json(_first_sale_of_each_item(orders)), "currency": currency},
    )
    return SavedDay(orders=len(orders), lines=sum(len(order.lines) for order in orders))


def _first_sale_of_each_item(orders: list[OrderRow]) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for order in orders:
        for line in order.lines:
            items.setdefault(
                line.pos_item_id,
                {"pos_item_id": line.pos_item_id, "name": line.item_name, "is_mock": order.is_mock},
            )
    return list(items.values())


def _order_values(order: OrderRow) -> dict[str, Any]:
    return {
        "pos_order_id": order.pos_order_id,
        "business_date": order.business_date,
        "opened_at": order.opened_at,
        "is_mock": order.is_mock,
    }


def _line_values(order: OrderRow, line: LineRow) -> dict[str, Any]:
    return {
        "pos_order_id": order.pos_order_id,
        "pos_line_id": line.pos_line_id,
        "pos_item_id": line.pos_item_id,
        "item_name": line.item_name,
        "quantity": line.quantity,
        "price": line.price,
        "modifiers": [
            {"pos_item_id": m.item_id, "name": m.item_name, "quantity": m.quantity}
            for m in line.modifiers
        ],
        "is_voided": line.is_voided,
        "is_mock": order.is_mock,
    }


def _json(rows: Sequence[Any]) -> str:
    """Rows (dicts or row dataclasses) as a JSON array. Decimals are sent as strings, so they
    stay exact."""
    values = [row if isinstance(row, dict) else asdict(row) for row in rows]
    return json.dumps(values, default=_json_value)


def _json_value(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):  # also covers datetime
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} cannot be sent as JSON.")


def _deactivate_missing(table: str, id_column: str) -> TextClause:
    """Only ever called with the fixed table and column names above, never outside input."""
    return text(f"""
        UPDATE {table} SET is_active = false, updated_at = CURRENT_TIMESTAMP
        WHERE restaurant_id = :restaurant_id AND provider = :provider AND is_mock = :is_mock
          AND is_active AND {id_column} <> ALL(CAST(:ids AS text[]))
    """)


_UPSERT_MENU_ITEMS = text("""
    INSERT INTO menu_items (restaurant_id, provider, pos_item_id, name, price, currency, is_mock)
    SELECT :restaurant_id, :provider, r.pos_item_id, r.name, r.price, r.currency, r.is_mock
    FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS r(
        pos_item_id text, name text, price numeric, currency text, is_mock boolean
    )
    ON CONFLICT (restaurant_id, provider, pos_item_id) DO UPDATE
    SET name = EXCLUDED.name, price = EXCLUDED.price, currency = EXCLUDED.currency,
        is_mock = EXCLUDED.is_mock, is_active = true, updated_at = CURRENT_TIMESTAMP
""")

_UPSERT_MODIFIERS = text("""
    INSERT INTO menu_modifiers (
        restaurant_id, provider, pos_modifier_id, name, group_name, price, is_mock
    )
    SELECT :restaurant_id, :provider, r.pos_modifier_id, r.name, r.group_name, r.price, r.is_mock
    FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS r(
        pos_modifier_id text, name text, group_name text, price numeric, is_mock boolean
    )
    ON CONFLICT (restaurant_id, provider, pos_modifier_id) DO UPDATE
    SET name = EXCLUDED.name, group_name = EXCLUDED.group_name, price = EXCLUDED.price,
        is_mock = EXCLUDED.is_mock, is_active = true, updated_at = CURRENT_TIMESTAMP
""")

_UPSERT_ORDERS = text("""
    INSERT INTO sales_orders (
        restaurant_id, provider, pos_order_id, business_date, opened_at, is_mock
    )
    SELECT :restaurant_id, :provider, r.pos_order_id, r.business_date, r.opened_at, r.is_mock
    FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS r(
        pos_order_id text, business_date date, opened_at timestamptz, is_mock boolean
    )
    ON CONFLICT (restaurant_id, provider, pos_order_id) DO UPDATE
    SET business_date = EXCLUDED.business_date, opened_at = EXCLUDED.opened_at,
        is_mock = EXCLUDED.is_mock, imported_at = CURRENT_TIMESTAMP
""")

_UPSERT_LINES = text("""
    INSERT INTO sales_order_lines (
        restaurant_id, sales_order_id, pos_line_id, pos_item_id, item_name, quantity, price,
        business_date, modifiers, is_voided
    )
    SELECT :restaurant_id, o.id, r.pos_line_id, r.pos_item_id, r.item_name, r.quantity,
        r.price, o.business_date, r.modifiers, r.is_voided
    FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS r(
        pos_order_id text, pos_line_id text, pos_item_id text, item_name text,
        quantity numeric, price numeric, modifiers jsonb, is_voided boolean
    )
    JOIN sales_orders AS o
      ON o.restaurant_id = :restaurant_id AND o.provider = :provider
     AND o.pos_order_id = r.pos_order_id
    ON CONFLICT (sales_order_id, pos_line_id) DO UPDATE
    SET pos_item_id = EXCLUDED.pos_item_id, item_name = EXCLUDED.item_name,
        quantity = EXCLUDED.quantity, price = EXCLUDED.price,
        business_date = EXCLUDED.business_date, modifiers = EXCLUDED.modifiers,
        is_voided = EXCLUDED.is_voided
""")

_VOID_MISSING_LINES = text("""
    UPDATE sales_order_lines AS line SET is_voided = true
    FROM sales_orders AS o
    WHERE line.sales_order_id = o.id
      AND line.restaurant_id = :restaurant_id
      AND o.restaurant_id = :restaurant_id AND o.provider = :provider
      AND o.pos_order_id = ANY(CAST(:order_ids AS text[]))
      AND NOT line.is_voided
      AND NOT EXISTS (
          SELECT 1 FROM jsonb_to_recordset(CAST(:rows AS jsonb))
              AS r(pos_order_id text, pos_line_id text)
          WHERE r.pos_order_id = o.pos_order_id AND r.pos_line_id = line.pos_line_id
      )
""")

_ADD_PLACEHOLDER_ITEMS = text("""
    INSERT INTO menu_items (
        restaurant_id, provider, pos_item_id, name, currency, is_active, is_mock
    )
    SELECT :restaurant_id, :provider, r.pos_item_id, r.name, :currency, false, r.is_mock
    FROM jsonb_to_recordset(CAST(:rows AS jsonb))
        AS r(pos_item_id text, name text, is_mock boolean)
    ON CONFLICT (restaurant_id, provider, pos_item_id) DO NOTHING
""")
