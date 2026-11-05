# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Translates Toast stock API responses into StockItem models.

What Toast's stock API can and cannot tell powr:

- Stock is tracked per menu item (and per modifier option, through its item reference),
  never per ingredient. Ingredient stock has to be derived from sales and recipes.
- ``GET /stock/v1/inventory`` lists only items that are ``OUT_OF_STOCK`` or limited
  (``QUANTITY``). Items that are ``IN_STOCK`` are left out, so an item missing from the
  response is in stock.
- A remaining amount is given only for ``QUANTITY`` items; it is null otherwise.
- The response has GUIDs but no item names; match them with the menu items.
- Standard API access is read-only, so ``POST /stock/v1/inventory/search`` answers 403.
"""

from typing import Any

from app.integrations.pos.models import PosConnection, StockItem
from app.integrations.pos.toast.client import ToastApiError

STOCK_PATH = "/stock/v1/inventory"
# Stock status -> is the item still available for sale?
AVAILABILITY_BY_STATUS = {"IN_STOCK": True, "QUANTITY": True, "OUT_OF_STOCK": False}


def stock_items_from_toast(body: Any, connection: PosConnection) -> list[StockItem]:
    if not isinstance(body, list):
        raise ToastApiError("Toast stock response is not a JSON array.")
    items: list[StockItem] = []
    for entry in body:
        guid = entry.get("guid")
        if not guid or entry.get("itemGuidValidity") == "INVALID":
            continue
        status = entry.get("status")
        items.append(
            StockItem(
                connection_id=connection.id,
                restaurant_id=connection.restaurant_id,
                item_id=guid,
                quantity=entry.get("quantity") if status == "QUANTITY" else None,
                is_available=AVAILABILITY_BY_STATUS.get(status),
            )
        )
    return items
