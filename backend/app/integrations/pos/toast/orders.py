# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Translates Toast ordersBulk responses into SaleLine models."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.integrations.pos.models import PosConnection, SaleLine, SaleModifier
from app.integrations.pos.toast.menus import MISSING_NAME

ORDERS_PATH = "/orders/v2/ordersBulk"
ORDERS_PAGE_SIZE = 100  # Toast's maximum page size for ordersBulk.
# Toast rejects date ranges longer than one month; a week stays well inside that.
ORDERS_WINDOW = timedelta(days=7)
# Gift card and house account lines move money but sell no food.
NON_FOOD_SELECTION_TYPES = frozenset(
    {"HOUSE_ACCOUNT_PAY_BALANCE", "TOAST_CARD_SELL", "TOAST_CARD_RELOAD"}
)


def order_windows(start: datetime, end: datetime) -> Iterator[tuple[datetime, datetime]]:
    """Split [start, end) into consecutive windows no longer than ORDERS_WINDOW."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start_time and end_time must be timezone-aware.")
    if start >= end:
        raise ValueError("start_time must be before end_time.")
    window_start = start
    while window_start < end:
        window_end = min(window_start + ORDERS_WINDOW, end)
        yield window_start, window_end
        window_start = window_end


def toast_datetime(value: datetime) -> str:
    """Format as Toast expects in query strings, e.g. 2026-10-01T04:00:00.000+0000."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0000"


def sale_lines_from_order(order: dict[str, Any], connection: PosConnection) -> Iterator[SaleLine]:
    """One SaleLine per sold menu item. Lines in voided or deleted orders, checks or items
    are kept with is_voided=True so the importer can undo them; refunded items are kept as
    sold because their ingredients were still used."""
    order_id = order.get("guid")
    opened = order.get("openedDate")
    business_date = _business_date(order.get("businessDate"))
    if not order_id or not opened or business_date is None:
        return
    order_voided = _is_voided(order)
    for check in order.get("checks") or []:
        check_voided = order_voided or _is_voided(check)
        for selection in check.get("selections") or []:
            if not _is_sold_menu_item(selection):
                continue
            yield SaleLine(
                connection_id=connection.id,
                restaurant_id=connection.restaurant_id,
                order_id=order_id,
                line_id=selection["guid"],
                item_id=selection["item"]["guid"],
                item_name=selection.get("displayName") or MISSING_NAME,
                quantity=selection["quantity"],
                timestamp=opened,
                business_date=business_date,
                price=_non_negative(selection.get("price")),
                modifiers=tuple(_sale_modifiers(selection.get("modifiers") or [])),
                is_voided=check_voided or _is_voided(selection),
            )


def _business_date(value: Any) -> date | None:
    """Toast sends the business date as a number like 20261001."""
    try:
        return datetime.strptime(str(value), "%Y%m%d").date()
    except ValueError:
        return None


def _is_voided(entity: dict[str, Any]) -> bool:
    return bool(entity.get("voided") or entity.get("deleted"))


def _is_sold_menu_item(selection: dict[str, Any]) -> bool:
    quantity = selection.get("quantity")
    return bool(
        selection.get("guid")
        and (selection.get("item") or {}).get("guid")
        and isinstance(quantity, (int, Decimal))
        and quantity > 0
        and not selection.get("deferred")
        and selection.get("selectionType") not in NON_FOOD_SELECTION_TYPES
    )


def _sale_modifiers(modifiers: list[Any]) -> Iterator[SaleModifier]:
    for modifier in modifiers:
        quantity = modifier.get("quantity")
        item_id = (modifier.get("item") or {}).get("guid")
        if modifier.get("voided") or not item_id or not isinstance(quantity, (int, Decimal)):
            continue
        if quantity > 0:
            yield SaleModifier(
                item_id=item_id,
                item_name=modifier.get("displayName") or MISSING_NAME,
                quantity=quantity,
            )


def _non_negative(value: Any) -> Decimal | None:
    if isinstance(value, (int, Decimal)) and value >= 0:
        return Decimal(value)
    return None
