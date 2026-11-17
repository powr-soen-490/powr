# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Saving imported menus and sales on a real database, with the recorded Toast week.

Each test runs in a throwaway database (see ``scratch_engine``).
"""

import json
import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.integrations.pos.models import PosConnection, SaleLine
from app.integrations.pos.toast.menus import menu_items_from_toast
from app.integrations.pos.toast.orders import sale_lines_from_order
from app.modules.pos.import_mapper import MenuRows, menu_rows, order_rows
from app.modules.pos.import_repository import save_menu, save_sales_day
from tests.unit.toast_fakes import RECORDED_WEEK_DIR

NOV_9 = date(2026, 11, 9)
TOAST = "TOAST"


@pytest.fixture
def db(migrated_engine: Engine) -> Iterator[Session]:
    with Session(migrated_engine) as session:
        yield session


def add_restaurant(db: Session, name: str = "Mykonos Grill") -> uuid.UUID:
    statement = text("INSERT INTO restaurants (name) VALUES (:name) RETURNING id")
    restaurant_id: uuid.UUID = db.execute(statement, {"name": name}).scalar_one()
    return restaurant_id


def connection_for(restaurant_id: uuid.UUID) -> PosConnection:
    return PosConnection(
        id=uuid.uuid4(), restaurant_id=restaurant_id, provider=TOAST, location_id="guid"
    )


def recorded(name: str) -> Any:
    return json.loads((RECORDED_WEEK_DIR / name).read_text(), parse_float=Decimal)


def recorded_lines(restaurant_id: uuid.UUID, day: date = NOV_9) -> list[SaleLine]:
    connection = connection_for(restaurant_id)
    orders = recorded(f"orders/{day}.json")
    return [line for order in orders for line in sale_lines_from_order(order, connection)]


def recorded_menu(restaurant_id: uuid.UUID) -> MenuRows:
    items = menu_items_from_toast(recorded("menus.json"), connection_for(restaurant_id), "USD")
    return menu_rows(items, restaurant_id)


def save_day(db: Session, restaurant_id: uuid.UUID, lines: list[SaleLine]) -> tuple[int, int]:
    saved = save_sales_day(
        db,
        restaurant_id=restaurant_id,
        provider=TOAST,
        currency="USD",
        orders=order_rows(lines, restaurant_id),
    )
    db.commit()
    return saved.orders, saved.lines


def count(db: Session, sql: str, restaurant_id: uuid.UUID) -> int:
    value: int = db.execute(text(sql), {"restaurant_id": restaurant_id}).scalar_one()
    return value


def line(db: Session, pos_line_id: str) -> Any:
    return (
        db.execute(
            text("SELECT * FROM sales_order_lines WHERE pos_line_id = :id"), {"id": pos_line_id}
        )
        .mappings()
        .one()
    )


def test_saving_a_day_twice_never_duplicates_orders(db: Session) -> None:
    restaurant_id = add_restaurant(db)
    lines = recorded_lines(restaurant_id)

    assert save_day(db, restaurant_id, lines) == (56, 110)
    assert save_day(db, restaurant_id, lines) == (56, 110)

    orders_sql = "SELECT count(*) FROM sales_orders WHERE restaurant_id = :restaurant_id"
    lines_sql = "SELECT count(*) FROM sales_order_lines WHERE restaurant_id = :restaurant_id"
    assert count(db, orders_sql, restaurant_id) == 56
    assert count(db, lines_sql, restaurant_id) == 110


def test_saved_lines_keep_exact_values_and_modifiers(db: Session) -> None:
    restaurant_id = add_restaurant(db)
    lines = recorded_lines(restaurant_id)
    with_modifier = next(sale for sale in lines if sale.modifiers)

    save_day(db, restaurant_id, lines)

    saved = line(db, with_modifier.line_id)
    assert saved["quantity"] == with_modifier.quantity
    assert saved["price"] == with_modifier.price
    assert saved["business_date"] == NOV_9
    assert saved["modifiers"] == [
        {"pos_item_id": m.item_id, "name": m.item_name, "quantity": str(m.quantity)}
        for m in with_modifier.modifiers
    ]


def test_a_later_void_is_applied(db: Session) -> None:
    restaurant_id = add_restaurant(db)
    lines = recorded_lines(restaurant_id)
    save_day(db, restaurant_id, lines)
    sold = next(sale for sale in lines if not sale.is_voided)

    voided = [
        sale.model_copy(update={"is_voided": True}) if sale == sold else sale for sale in lines
    ]
    save_day(db, restaurant_id, voided)

    assert line(db, sold.line_id)["is_voided"] is True


def test_a_line_missing_from_its_order_is_voided_not_deleted(db: Session) -> None:
    restaurant_id = add_restaurant(db)
    lines = recorded_lines(restaurant_id)
    save_day(db, restaurant_id, lines)
    order_id = next(sale.order_id for sale in lines if not sale.is_voided)
    order_lines = [sale for sale in lines if sale.order_id == order_id]
    removed = order_lines[0]

    save_day(db, restaurant_id, [sale for sale in order_lines if sale != removed])

    assert line(db, removed.line_id)["is_voided"] is True
    # Orders that were not fetched again are left alone.
    still_sold = next(s for s in lines if s.order_id != order_id and not s.is_voided)
    assert line(db, still_sold.line_id)["is_voided"] is False


def test_items_sold_but_not_on_the_menu_become_inactive_menu_items(db: Session) -> None:
    restaurant_id = add_restaurant(db)
    menu = recorded_menu(restaurant_id)
    save_menu(db, restaurant_id=restaurant_id, provider=TOAST, menu=menu)
    lines = recorded_lines(restaurant_id)
    on_menu = {row.pos_item_id for row in menu.items}
    # The first sale of an item that is not on the menu names its placeholder.
    old_item = next(sale for sale in lines if sale.item_id not in on_menu)

    save_day(db, restaurant_id, lines)

    row = db.execute(
        text("SELECT name, is_active, price FROM menu_items WHERE pos_item_id = :id"),
        {"id": old_item.item_id},
    ).one()
    assert tuple(row) == (old_item.item_name, False, None)
    active_sql = (
        "SELECT count(*) FROM menu_items WHERE restaurant_id = :restaurant_id AND is_active"
    )
    assert count(db, active_sql, restaurant_id) == len(menu.items)


def test_saving_the_menu_twice_keeps_one_row_per_item(db: Session) -> None:
    restaurant_id = add_restaurant(db)
    menu = recorded_menu(restaurant_id)

    for _ in range(2):
        save_menu(db, restaurant_id=restaurant_id, provider=TOAST, menu=menu)
        db.commit()

    items_sql = "SELECT count(*) FROM menu_items WHERE restaurant_id = :restaurant_id"
    modifiers_sql = "SELECT count(*) FROM menu_modifiers WHERE restaurant_id = :restaurant_id"
    assert count(db, items_sql, restaurant_id) == len(menu.items) == 214
    assert count(db, modifiers_sql, restaurant_id) == len(menu.modifiers)


def test_items_removed_from_the_menu_become_inactive_and_come_back(db: Session) -> None:
    restaurant_id = add_restaurant(db)
    menu = recorded_menu(restaurant_id)
    save_menu(db, restaurant_id=restaurant_id, provider=TOAST, menu=menu)
    removed = menu.items[0]

    smaller = MenuRows(items=menu.items[1:], modifiers=menu.modifiers[1:])
    save_menu(db, restaurant_id=restaurant_id, provider=TOAST, menu=smaller)
    status_sql = "SELECT is_active FROM menu_items WHERE pos_item_id = :id"
    assert db.execute(text(status_sql), {"id": removed.pos_item_id}).scalar_one() is False
    inactive_sql = (
        "SELECT count(*) FROM menu_modifiers WHERE restaurant_id = :restaurant_id AND NOT is_active"
    )
    assert count(db, inactive_sql, restaurant_id) == 1

    save_menu(db, restaurant_id=restaurant_id, provider=TOAST, menu=menu)
    assert db.execute(text(status_sql), {"id": removed.pos_item_id}).scalar_one() is True


def test_an_empty_menu_deactivates_nothing(db: Session) -> None:
    restaurant_id = add_restaurant(db)
    save_menu(db, restaurant_id=restaurant_id, provider=TOAST, menu=recorded_menu(restaurant_id))

    save_menu(db, restaurant_id=restaurant_id, provider=TOAST, menu=MenuRows([], []))

    inactive_sql = (
        "SELECT count(*) FROM menu_items WHERE restaurant_id = :restaurant_id AND NOT is_active"
    )
    assert count(db, inactive_sql, restaurant_id) == 0


def test_restaurants_never_touch_each_others_sales(db: Session) -> None:
    mykonos = add_restaurant(db)
    other = add_restaurant(db, "Other Grill")
    save_day(db, mykonos, recorded_lines(mykonos))

    # The other restaurant has the same Toast IDs but fewer lines in each order.
    other_lines = recorded_lines(other)
    save_day(db, other, [sale for sale in other_lines if sale.line_id != other_lines[0].line_id])

    voided_sql = (
        "SELECT count(*) FROM sales_order_lines WHERE restaurant_id = :restaurant_id AND is_voided"
    )
    mykonos_voided = sum(sale.is_voided for sale in recorded_lines(mykonos))
    assert count(db, voided_sql, mykonos) == mykonos_voided
    lines_sql = "SELECT count(*) FROM sales_order_lines WHERE restaurant_id = :restaurant_id"
    assert count(db, lines_sql, mykonos) == 110
    assert count(db, lines_sql, other) == 109


def test_an_empty_day_saves_nothing(db: Session) -> None:
    assert save_day(db, add_restaurant(db), []) == (0, 0)
