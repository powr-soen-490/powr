# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""The sales summary on a real database: real owner sessions and imported sales."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, tzinfo
from decimal import Decimal
from typing import Any, Self

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.api import toast as toast_api
from app.integrations.pos.models import SaleLine
from app.modules.pos.import_mapper import order_rows
from app.modules.pos.import_repository import save_sales_day

OCT_9 = date(2026, 10, 9)
OCT_10 = date(2026, 10, 10)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        return cls(2026, 10, 10, 12, tzinfo=UTC)


def line(restaurant_id: uuid.UUID, order_id: str, day: date, **values: Any) -> SaleLine:
    fields: dict[str, Any] = {
        "connection_id": uuid.uuid4(),
        "restaurant_id": restaurant_id,
        "order_id": order_id,
        "line_id": f"{order_id}-{values.pop('line', 'a')}",
        "item_id": "item-gyro",
        "item_name": "Gyro plate",
        "quantity": Decimal("1"),
        "timestamp": datetime(day.year, day.month, day.day, 18, tzinfo=UTC),
        "business_date": day,
        "price": Decimal("10"),
    }
    return SaleLine.model_validate(fields | values)


def save(engine: Engine, restaurant_id: uuid.UUID, lines: list[SaleLine]) -> None:
    with Session(engine) as db:
        save_sales_day(
            db,
            restaurant_id=restaurant_id,
            provider="TOAST",
            currency="USD",
            orders=order_rows(lines, restaurant_id),
        )
        db.commit()


def test_owner_sees_only_their_imported_sales(
    make_client: Callable[[], TestClient],
    sign_up_owner: Callable[[TestClient, str], dict[str, Any]],
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(toast_api, "datetime", FrozenDateTime)
    client = make_client()
    owner = uuid.UUID(sign_up_owner(client, "owner@example.com")["restaurant_id"])
    other = uuid.UUID(sign_up_owner(make_client(), "other@example.com")["restaurant_id"])

    # Nothing imported yet: empty totals, not an error, and no Toast connection needed.
    empty = client.get("/api/pos/toast/sales-summary?days=1")
    assert empty.status_code == 200
    assert (empty.json()["total_orders"], empty.json()["daily_stats"]) == (0, [])

    save(
        migrated_engine,
        owner,
        [
            line(owner, "one", OCT_9, quantity=Decimal("2"), price=Decimal("20")),
            line(owner, "one", OCT_9, line="b", quantity=Decimal("0.35"), price=Decimal("4.20")),
            line(owner, "one", OCT_9, line="void", price=Decimal("7"), is_voided=True),
            line(owner, "refunded", OCT_10, price=Decimal("30")),  # refunds count as sold
            line(owner, "mock", OCT_10, price=Decimal("99"), is_mock=True),
            line(owner, "old", date(2026, 10, 8), price=Decimal("99")),
        ],
    )
    save(migrated_engine, other, [line(other, "one", OCT_10, price=Decimal("99"))])

    response = client.get("/api/pos/toast/sales-summary?days=1")

    assert response.status_code == 200
    body = response.json()
    assert (body["start_date"], body["end_date"]) == ("2026-10-09", "2026-10-10")
    assert (body["total_orders"], Decimal(body["total_items"])) == (2, Decimal("3.35"))
    assert Decimal(body["total_revenue"]) == Decimal("54.20")
    assert [
        (day["date"], day["orders"], Decimal(day["items"]), Decimal(day["revenue"]))
        for day in body["daily_stats"]
    ] == [
        ("2026-10-09", 1, Decimal("2.35"), Decimal("24.20")),
        ("2026-10-10", 1, Decimal("1"), Decimal("30")),
    ]
