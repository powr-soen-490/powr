# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Mock POS data (menu items and sales) in the internal model shape, for testing without a POS.

From backend/:
    python -m app.integrations.pos.mock --restaurant <uuid> --type menu --seed 42
    python -m app.integrations.pos.mock --restaurant <uuid> --type sales \
        --start 2026-08-01 --end 2026-10-31 --seed 42
"""

import argparse
import random
import sys
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from pydantic import TypeAdapter

from app.core.config import get_settings
from app.integrations.pos.models import MenuItem, SaleLine

# (name, price, popularity weight)
MOCK_MENU: tuple[tuple[str, str, int], ...] = (
    ("Chicken Gyro", "12.95", 10),
    ("Lamb Gyro", "13.95", 7),
    ("Falafel Wrap", "11.50", 5),
    ("Greek Salad", "10.95", 6),
    ("Chicken Souvlaki Plate", "17.95", 6),
    ("Moussaka", "18.50", 3),
    ("Spanakopita", "8.95", 4),
    ("Hummus & Pita", "7.95", 5),
    ("Greek Fries", "5.95", 8),
    ("Baklava", "5.50", 4),
)
MOCK_TIMEZONE = ZoneInfo("America/New_York")
# Calibrated to a real 30-day Toast pull: about 55 orders and 2.4 items per order a day.
BASE_ORDERS_PER_DAY = 55
WEEKDAY_FACTORS = (0.85, 0.85, 0.95, 1.0, 1.25, 1.3, 1.1)  # Monday first
LUNCH_SHARE = 0.4

MENU_ADAPTER = TypeAdapter(list[MenuItem])
SALES_ADAPTER = TypeAdapter(list[SaleLine])


def mock_connection_id(restaurant_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"mock:{restaurant_id}")


def generate_menu(restaurant_id: UUID) -> list[MenuItem]:
    return [
        MenuItem(
            connection_id=mock_connection_id(restaurant_id),
            restaurant_id=restaurant_id,
            item_id=f"mock-item-{index}",
            item_name=name,
            price=Decimal(price),
            currency="USD",
            is_mock=True,
        )
        for index, (name, price, _) in enumerate(MOCK_MENU, start=1)
    ]


def _order_time(day: date, rng: random.Random) -> datetime:
    """A local time around the lunch or dinner peak."""
    if rng.random() < LUNCH_SHARE:
        hours = min(max(rng.gauss(12.5, 0.75), 11.0), 14.9)
    else:
        hours = min(max(rng.gauss(19.0, 1.0), 17.0), 21.9)
    minutes = int(hours * 60)
    return datetime.combine(day, time(minutes // 60, minutes % 60), tzinfo=MOCK_TIMEZONE)


def _order_lines(
    menu: Sequence[MenuItem], weights: Sequence[int], order_id: str, day: date, rng: random.Random
) -> list[SaleLine]:
    timestamp = _order_time(day, rng)
    line_count = rng.choices((1, 2, 3), weights=(3, 4, 3))[0]
    lines = []
    for number, item in enumerate(rng.choices(menu, weights=weights, k=line_count), start=1):
        quantity = Decimal(rng.choices((1, 2), weights=(4, 1))[0])
        lines.append(
            SaleLine(
                connection_id=item.connection_id,
                restaurant_id=item.restaurant_id,
                order_id=order_id,
                line_id=f"{order_id}-{number}",
                item_id=item.item_id,
                item_name=item.item_name,
                quantity=quantity,
                timestamp=timestamp,
                business_date=day,
                price=item.price * quantity if item.price is not None else None,
                is_mock=True,
            )
        )
    return lines


def generate_sales(
    menu: Sequence[MenuItem], start: date, end: date, rng: random.Random
) -> list[SaleLine]:
    """Sale lines for each business day in the inclusive range, using only the given menu."""
    if not menu:
        raise ValueError("Cannot generate sales without menu items")
    popularity = {name: weight for name, _, weight in MOCK_MENU}
    weights = [popularity.get(item.item_name, 1) for item in menu]
    lines: list[SaleLine] = []
    day = start
    while day <= end:
        expected = BASE_ORDERS_PER_DAY * WEEKDAY_FACTORS[day.weekday()]
        orders = max(1, round(rng.gauss(expected, expected * 0.1)))
        for number in range(1, orders + 1):
            order_id = f"mock-order-{day.isoformat()}-{number}"
            lines.extend(_order_lines(menu, weights, order_id, day, rng))
        day += timedelta(days=1)
    return lines


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate mock POS menu items or sales as JSON.")
    parser.add_argument("--restaurant", type=UUID, required=True, help="restaurant UUID")
    parser.add_argument("--type", choices=("menu", "sales"), required=True, dest="data_type")
    parser.add_argument("--start", type=date.fromisoformat, help="first sales day, YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, help="last sales day, YYYY-MM-DD")
    parser.add_argument("--seed", type=int, help="same seed gives the same data")
    parser.add_argument("--out-dir", type=Path, default=Path("mock_data"))
    args = parser.parse_args(argv)
    if args.data_type == "sales":
        if args.start is None or args.end is None:
            parser.error("--start and --end are required with --type sales")
        if args.start > args.end:
            parser.error("--start must not be after --end")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if get_settings().environment == "production":
        sys.exit("Mock POS data generation is disabled in production")
    out_dir: Path = args.out_dir / str(args.restaurant)
    menu_path = out_dir / "menu.json"
    if args.data_type == "menu":
        out_dir.mkdir(parents=True, exist_ok=True)
        menu_path.write_bytes(MENU_ADAPTER.dump_json(generate_menu(args.restaurant), indent=2))
        print(f"Wrote {menu_path}")
        return
    if not menu_path.is_file():
        sys.exit(
            f"No mock menu for restaurant {args.restaurant} at {menu_path}; "
            "run with --type menu first"
        )
    menu = MENU_ADAPTER.validate_json(menu_path.read_bytes())
    sales = generate_sales(menu, args.start, args.end, random.Random(args.seed))
    sales_path = out_dir / "sales.json"
    sales_path.write_bytes(SALES_ADAPTER.dump_json(sales, indent=2))
    print(f"Wrote {len(sales)} sale lines to {sales_path}")


if __name__ == "__main__":
    main()
