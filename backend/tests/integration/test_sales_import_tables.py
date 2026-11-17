# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Integration tests for issue #53: db/06_pos_sales_import.sql, migrated up and down.

Each test runs in a throwaway database (see ``scratch_engine``), so nothing here touches a
developer's own data.
"""

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.database import migrate_down, migrate_up

SALES_IMPORT_TABLES = {
    "menu_items",
    "menu_modifiers",
    "sales_orders",
    "sales_order_lines",
    "sync_jobs",
}
OLD_PLACEHOLDER_TABLES = {"pos_orders", "pos_order_line_items"}
NOV_9 = date(2026, 11, 9)


@pytest.fixture
def migrated(scratch_engine: Engine) -> Iterator[Connection]:
    migrate_up(scratch_engine)
    with scratch_engine.connect() as connection:
        yield connection


def table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def add_restaurant(connection: Connection, name: str = "Mykonos Grill") -> uuid.UUID:
    statement = text("INSERT INTO restaurants (name) VALUES (:name) RETURNING id")
    restaurant_id: uuid.UUID = connection.execute(statement, {"name": name}).scalar_one()
    return restaurant_id


def add_order(connection: Connection, restaurant_id: uuid.UUID, pos_order_id: str) -> uuid.UUID:
    statement = text(
        "INSERT INTO sales_orders (restaurant_id, provider, pos_order_id, business_date, "
        "opened_at) VALUES (:restaurant_id, 'TOAST', :pos_order_id, :day, now()) RETURNING id"
    )
    params = {"restaurant_id": restaurant_id, "pos_order_id": pos_order_id, "day": NOV_9}
    order_id: uuid.UUID = connection.execute(statement, params).scalar_one()
    return order_id


def add_line(
    connection: Connection,
    restaurant_id: uuid.UUID,
    order_id: uuid.UUID,
    quantity: Decimal = Decimal("1"),
) -> None:
    connection.execute(
        text(
            "INSERT INTO sales_order_lines (restaurant_id, sales_order_id, pos_line_id, "
            "pos_item_id, item_name, quantity, business_date) VALUES (:restaurant_id, "
            ":order_id, 'line-1', 'item-gyro', 'Gyro plate', :quantity, :day)"
        ),
        {
            "restaurant_id": restaurant_id,
            "order_id": order_id,
            "quantity": quantity,
            "day": NOV_9,
        },
    )


def add_job(connection: Connection, restaurant_id: uuid.UUID, status: str) -> None:
    connection.execute(
        text(
            "INSERT INTO sync_jobs (restaurant_id, provider, status, start_date, end_date) "
            "VALUES (:restaurant_id, 'TOAST', :status, '2024-01-01', '2026-11-15')"
        ),
        {"restaurant_id": restaurant_id, "status": status},
    )


def test_migration_runs_up_and_down_cleanly(scratch_engine: Engine) -> None:
    migrate_up(scratch_engine)
    migrate_up(scratch_engine)  # running it twice changes nothing
    assert table_names(scratch_engine) >= SALES_IMPORT_TABLES
    assert table_names(scratch_engine).isdisjoint(OLD_PLACEHOLDER_TABLES)

    migrate_down(scratch_engine)
    assert table_names(scratch_engine).isdisjoint(SALES_IMPORT_TABLES)
    assert "restaurants" in table_names(scratch_engine)

    migrate_up(scratch_engine)
    assert table_names(scratch_engine) >= SALES_IMPORT_TABLES


def test_migrating_again_keeps_imported_sales(scratch_engine: Engine) -> None:
    migrate_up(scratch_engine)
    with scratch_engine.begin() as connection:
        restaurant_id = add_restaurant(connection)
        add_line(connection, restaurant_id, add_order(connection, restaurant_id, "order-1"))

    migrate_up(scratch_engine)

    with scratch_engine.connect() as connection:
        lines = connection.execute(text("SELECT count(*) FROM sales_order_lines")).scalar_one()
    assert lines == 1


def test_migration_removes_the_old_placeholder_tables(scratch_engine: Engine) -> None:
    """A database made before #53 still has the placeholders from the old 01_init.sql."""
    migrate_up(scratch_engine)
    with scratch_engine.begin() as connection:
        connection.execute(text("CREATE TABLE pos_orders (id UUID PRIMARY KEY)"))
        connection.execute(
            text("CREATE TABLE pos_order_line_items (pos_order_id UUID REFERENCES pos_orders)")
        )

    migrate_up(scratch_engine)

    assert table_names(scratch_engine).isdisjoint(OLD_PLACEHOLDER_TABLES)


def test_an_order_is_saved_once_per_restaurant(migrated: Connection) -> None:
    restaurant_id = add_restaurant(migrated)
    add_order(migrated, restaurant_id, "order-1")
    add_order(migrated, add_restaurant(migrated, "Other Grill"), "order-1")

    with pytest.raises(IntegrityError, match="sales_orders_restaurant_id_provider_pos_order_id"):
        add_order(migrated, restaurant_id, "order-1")


def test_a_line_must_belong_to_an_order_of_the_same_restaurant(migrated: Connection) -> None:
    order_id = add_order(migrated, add_restaurant(migrated), "order-1")
    other_restaurant_id = add_restaurant(migrated, "Other Grill")

    with pytest.raises(IntegrityError, match="sales_order_lines_sales_order_id_restaurant_id"):
        add_line(migrated, other_restaurant_id, order_id)


def test_quantities_keep_their_decimals(migrated: Connection) -> None:
    restaurant_id = add_restaurant(migrated)
    add_line(
        migrated, restaurant_id, add_order(migrated, restaurant_id, "order-1"), Decimal("0.35")
    )

    saved = migrated.execute(text("SELECT quantity FROM sales_order_lines")).scalar_one()
    assert saved == Decimal("0.35")


def test_only_one_import_runs_at_a_time(migrated: Connection) -> None:
    restaurant_id = add_restaurant(migrated)
    add_job(migrated, restaurant_id, "done")
    add_job(migrated, restaurant_id, "failed")
    add_job(migrated, restaurant_id, "running")
    add_job(migrated, add_restaurant(migrated, "Other Grill"), "running")

    with pytest.raises(IntegrityError, match="uq_sync_jobs_one_running"):
        add_job(migrated, restaurant_id, "running")


def test_a_job_status_must_be_known(migrated: Connection) -> None:
    with pytest.raises(IntegrityError, match="sync_jobs_status_check"):
        add_job(migrated, add_restaurant(migrated), "paused")
