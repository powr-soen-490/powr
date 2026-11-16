# Source-File AI Declaration
# AI contribution: 50% or more AI-generated

"""
Rebuild the real-menu dataset that the mock POS generator samples menus from.

Source: "New York Restaurant Menus and Details" by Anoop Johny on Kaggle, MIT License:
https://www.kaggle.com/datasets/anoopjohny/new-york-restaurant-menus-and-details
Dine-in menus of New York restaurants from allmenus.com (2024). This script keeps priced items,
uses the base price of size-priced items ("$7.50+"), drops add-ons, cans and catering trays by
price, and keeps restaurants whose menu size is typical of an independent restaurant.

    curl -L -o menus.zip https://www.kaggle.com/api/v1/datasets/download/anoopjohny/new-york-restaurant-menus-and-details
    unzip menus.zip -d menus
    python scripts/build_mock_menu_dataset.py menus
"""

import csv
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

OUTPUT = (
    Path(__file__).resolve().parents[1] / "backend/app/integrations/pos/data/mock_menu_items.csv"
)
MIN_ITEMS, MAX_ITEMS = 25, 100  # per restaurant
# Below MIN_PRICE are add-ons and canned drinks; above MAX_PRICE, catering trays.
MIN_PRICE, MAX_PRICE = Decimal("3"), Decimal("200")
MAX_NAME_LENGTH = 255  # MenuItem.item_name limit


def _price(text: str) -> Decimal | None:
    try:
        price = Decimal(text.strip().removeprefix("$").removesuffix("+").replace(",", ""))
    except InvalidOperation:
        return None
    return price if MIN_PRICE <= price <= MAX_PRICE else None


def _fix_encoding(text: str) -> str:
    """Undo double-encoded UTF-8 in the source, e.g. "PurÃ©ed" -> "Puréed"."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return text


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def main(source: Path) -> None:
    cuisines: dict[str, str] = {}
    for row in _read(source / "restaurant_data.csv"):
        cuisines.setdefault(row["Name"].strip(), row["Cuisine"].strip())
    items: dict[tuple[str, str], Decimal] = {}
    for row in _read(source / "menu_data.csv"):
        restaurant = row["Restaurant"].strip()
        name = _fix_encoding(row["Item"]).strip()[:MAX_NAME_LENGTH]
        price = _price(row["Price"])
        if restaurant and name and price is not None:
            items.setdefault((restaurant, name), price)
    counts = Counter(restaurant for restaurant, _ in items)
    rows = sorted(
        (restaurant, cuisines.get(restaurant, ""), name, price)
        for (restaurant, name), price in items.items()
        if MIN_ITEMS <= counts[restaurant] <= MAX_ITEMS
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("restaurant", "cuisine", "item_name", "price"))
        writer.writerows(rows)
    print(f"Wrote {len(rows)} items from {len({row[0] for row in rows})} restaurants")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/build_mock_menu_dataset.py <unzipped dataset folder>")
    main(Path(sys.argv[1]))
