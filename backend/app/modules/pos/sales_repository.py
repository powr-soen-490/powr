# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Database reads of imported POS sales."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class DailySales:
    business_date: date
    orders: int
    items: Decimal
    revenue: Decimal


def daily_sales(
    db: Session, *, restaurant_id: UUID, provider: str, start_date: date, end_date: date
) -> list[DailySales]:
    """Totals per business day, from start_date to end_date inclusive, for days with sales.

    Same rule as the import: voided lines are left out and refunded ones count as sold.
    Generated (mock) data is left out too.
    """
    rows = db.execute(
        text("""
            SELECT line.business_date,
                   count(DISTINCT line.sales_order_id) AS orders,
                   sum(line.quantity) AS items,
                   coalesce(sum(line.price), 0) AS revenue
            FROM sales_order_lines AS line
            JOIN sales_orders AS o
              ON o.id = line.sales_order_id AND o.restaurant_id = line.restaurant_id
            WHERE line.restaurant_id = :restaurant_id AND o.provider = :provider
              AND line.business_date BETWEEN :start_date AND :end_date
              AND NOT line.is_voided AND NOT o.is_mock
            GROUP BY line.business_date
            ORDER BY line.business_date
        """),
        {
            "restaurant_id": restaurant_id,
            "provider": provider,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    return [
        DailySales(business_date=row[0], orders=row[1], items=row[2], revenue=row[3])
        for row in rows
    ]
