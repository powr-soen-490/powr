# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""The menu mapping list through the API: statuses, coverage and revenue order."""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, text

ClientFactory = Callable[[], TestClient]
SignUp = Callable[[TestClient, str], dict[str, Any]]


def insert(connection: Connection, sql: str, **values: Any) -> str:
    return str(connection.execute(text(sql), values).scalar_one())


def add_item(connection: Connection, restaurant_id: str, name: str, **extra: Any) -> str:
    return insert(
        connection,
        """
        INSERT INTO menu_items (restaurant_id, provider, pos_item_id, name, price, currency,
                                is_active)
        VALUES (:restaurant_id, 'TOAST', :name, :name, 10, 'USD', :is_active) RETURNING id
        """,
        restaurant_id=restaurant_id,
        name=name,
        is_active=extra.get("is_active", True),
    )


def add_sale(
    connection: Connection, restaurant_id: str, item: str, price: str, modifiers: list[str]
) -> None:
    """One order of one line, a few days ago. Items and modifiers use their name as POS id."""
    day = (datetime.now(UTC) - timedelta(days=3)).date()
    order_id = insert(
        connection,
        """
        INSERT INTO sales_orders (restaurant_id, provider, pos_order_id, business_date, opened_at)
        VALUES (:restaurant_id, 'TOAST', :pos_order_id, :day, :day) RETURNING id
        """,
        restaurant_id=restaurant_id,
        pos_order_id=str(uuid.uuid4()),
        day=day,
    )
    connection.execute(
        text("""
            INSERT INTO sales_order_lines (restaurant_id, sales_order_id, pos_line_id,
                pos_item_id, item_name, quantity, price, business_date, modifiers)
            VALUES (:restaurant_id, :order_id, 'line-1', :item, :item, 1, :price, :day,
                    CAST(:modifiers AS jsonb))
        """),
        {
            "restaurant_id": restaurant_id,
            "order_id": order_id,
            "item": item,
            "price": Decimal(price),
            "day": day,
            "modifiers": json.dumps(
                [{"pos_item_id": m, "name": m, "quantity": "1"} for m in modifiers]
            ),
        },
    )


def test_statuses_coverage_and_revenue_order(
    make_client: ClientFactory, sign_up_owner: SignUp, migrated_engine: Engine
) -> None:
    owner = make_client()
    restaurant_id = sign_up_owner(owner, "owner@mykonos.example")["restaurant_id"]
    with migrated_engine.begin() as connection:
        ids = {
            name: add_item(connection, restaurant_id, name)
            for name in ["Souvlaki plate", "Gyro", "Dolmades", "Horiatiki"]
        }
        add_item(connection, restaurant_id, "Old special", is_active=False)  # never shown
        for modifier in ["Extra feta", "Add tzatziki"]:
            ids[modifier] = insert(
                connection,
                """
                INSERT INTO menu_modifiers (restaurant_id, provider, pos_modifier_id, name,
                                            group_name)
                VALUES (:restaurant_id, 'TOAST', :name, :name, 'Add-ons') RETURNING id
                """,
                restaurant_id=restaurant_id,
                name=modifier,
            )
        add_sale(connection, restaurant_id, "Souvlaki plate", "100", ["Extra feta"])
        add_sale(connection, restaurant_id, "Gyro", "20", ["Add tzatziki"])
        add_sale(connection, restaurant_id, "Dolmades", "50", [])
        add_sale(connection, restaurant_id, "Horiatiki", "30", [])

    feta = owner.post("/api/ingredients", json={"name": "Feta", "base_unit": "g"}).json()["id"]
    for dish, modifier_lines in [
        ("Souvlaki plate", [{"menu_modifier_id": ids["Extra feta"], "effect": "add"}]),
        ("Gyro", []),  # "Add tzatziki" sells with it but is not mapped: needs review
    ]:
        response = owner.put(
            f"/api/menu-items/{ids[dish]}/recipe",
            json={
                "lines": [{"ingredient_id": feta, "quantity": "60", "unit": "g"}],
                "modifier_lines": [
                    {**line, "ingredient_id": feta, "quantity": "30", "unit": "g"}
                    for line in modifier_lines
                ],
            },
        )
        assert response.status_code == 201, response.text

    body = owner.get("/api/menu-items").json()
    assert [(item["name"], item["status"]) for item in body["items"]] == [
        ("Dolmades", "unmapped"),  # unmapped first, highest revenue first
        ("Horiatiki", "unmapped"),
        ("Gyro", "needs_review"),
        ("Souvlaki plate", "mapped"),
    ]
    gyro = body["items"][2]
    assert (gyro["review_reasons"], gyro["unmapped_modifiers"]) == (
        ["unmapped_modifier"],
        ["Add tzatziki"],
    )
    coverage = body["coverage"]
    assert Decimal(coverage["item_share"]) == Decimal("0.5")  # 2 of 4 items
    assert Decimal(coverage["revenue_share"]) == Decimal("0.6")  # $120 of $200

    unmapped = owner.get("/api/menu-items", params={"status": "unmapped"}).json()
    assert [item["name"] for item in unmapped["items"]] == ["Dolmades", "Horiatiki"]
    assert unmapped["coverage"] == coverage
