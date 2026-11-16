# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Records real Toast responses as scrubbed files, so tests and local dev run without Toast.

Scrubbing works from an allow-list: only the fields powr reads (plus a few harmless ones
that keep the files readable) are copied. Customers, employees, payments, delivery addresses
and any field Toast adds later are never copied, and the restaurant GUID is swapped for a
fake one, because the repository is public.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from app.integrations.pos.toast.client import ToastApiError, ToastClient
from app.integrations.pos.toast.menus import MENUS_PATH
from app.integrations.pos.toast.orders import orders_on_business_date

FAKE_RESTAURANT_GUID = "00000000-0000-0000-0000-0000000f1c75"


class Keep(Enum):
    """How to copy an allow-listed field that holds plain values."""

    VALUE = "value"  # one string, number, boolean or null
    VALUES = "values"  # a list of those


@dataclass(frozen=True)
class ById:
    """A JSON object keyed by IDs, where every value follows ``spec``."""

    spec: "Spec"


type Rule = Keep | ById | Spec
# The fields to copy from an object (or from every object in a list), each with its rule.
type Spec = dict[str, Rule]

# --- Orders: what orders.py reads, plus refund amounts to show that refunds count as sold.
ITEM_REFERENCE: Spec = {"guid": Keep.VALUE}
ORDER_MODIFIER: Spec = {
    "guid": Keep.VALUE,
    "item": ITEM_REFERENCE,
    "displayName": Keep.VALUE,
    "quantity": Keep.VALUE,
    "price": Keep.VALUE,
    "voided": Keep.VALUE,
}
REFUND_DETAILS: Spec = {"refundAmount": Keep.VALUE, "taxRefundAmount": Keep.VALUE}
SELECTION: Spec = {
    "guid": Keep.VALUE,
    "item": ITEM_REFERENCE,
    "displayName": Keep.VALUE,
    "selectionType": Keep.VALUE,
    "quantity": Keep.VALUE,
    "price": Keep.VALUE,
    "voided": Keep.VALUE,
    "deleted": Keep.VALUE,
    "deferred": Keep.VALUE,
    "modifiers": ORDER_MODIFIER,
    "refundDetails": REFUND_DETAILS,
}
CHECK: Spec = {
    "guid": Keep.VALUE,
    "voided": Keep.VALUE,
    "deleted": Keep.VALUE,
    "selections": SELECTION,
}
ORDER: Spec = {
    "guid": Keep.VALUE,
    "openedDate": Keep.VALUE,
    "modifiedDate": Keep.VALUE,
    "businessDate": Keep.VALUE,
    "voided": Keep.VALUE,
    "deleted": Keep.VALUE,
    "checks": CHECK,
}

# --- Menus: what menus.py reads, plus menu and group names to keep the files readable.
MODIFIER_OPTION: Spec = {
    "referenceId": Keep.VALUE,
    "guid": Keep.VALUE,
    "name": Keep.VALUE,
    "price": Keep.VALUE,
}
MODIFIER_GROUP: Spec = {
    "referenceId": Keep.VALUE,
    "guid": Keep.VALUE,
    "name": Keep.VALUE,
    "minSelections": Keep.VALUE,
    "maxSelections": Keep.VALUE,
    "modifierOptionReferences": Keep.VALUES,
}
MENU_ITEM: Spec = {
    "guid": Keep.VALUE,
    "name": Keep.VALUE,
    "price": Keep.VALUE,
    "modifierGroupReferences": Keep.VALUES,
}
MENU_GROUP: Spec = {"guid": Keep.VALUE, "name": Keep.VALUE, "menuItems": MENU_ITEM}
MENU_GROUP["menuGroups"] = MENU_GROUP  # menu groups can hold more menu groups
MENU: Spec = {"guid": Keep.VALUE, "name": Keep.VALUE, "menuGroups": MENU_GROUP}
MENUS: Spec = {
    "restaurantGuid": Keep.VALUE,
    "lastUpdated": Keep.VALUE,
    "restaurantTimeZone": Keep.VALUE,
    "menus": MENU,
    "modifierGroupReferences": ById(MODIFIER_GROUP),
    "modifierOptionReferences": ById(MODIFIER_OPTION),
}

# Patterns that should never appear in a scrubbed file. GUIDs are skipped before checking,
# since their digit groups can look like a card number.
GUID = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
PERSONAL_DATA = {
    "email address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "card number": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "phone number": re.compile(r"\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b"),
}


@dataclass(frozen=True)
class RecordedDays:
    """Scrubbed Toast responses: the menu, and the orders of each business day."""

    menus: dict[str, Any]
    orders_by_day: dict[date, list[Any]]

    def files(self) -> dict[str, Any]:
        """The file contents to save, by path relative to the output folder."""
        files: dict[str, Any] = {"menus.json": self.menus}
        for day, orders in self.orders_by_day.items():
            files[f"orders/{day.isoformat()}.json"] = orders
        return files


def scrub(value: Any, rule: Rule) -> Any:
    """Copy only what ``rule`` allows. A value of an unexpected shape becomes None, so a
    nested object never slips through where a plain value was expected."""
    if rule is Keep.VALUE:
        return value if _is_plain(value) else None
    if rule is Keep.VALUES:
        return [item for item in value if _is_plain(item)] if isinstance(value, list) else None
    if isinstance(rule, ById):
        if not isinstance(value, dict):
            return None
        return {str(key): scrub(item, rule.spec) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item, rule) for item in value]
    if isinstance(value, dict):
        return {key: scrub(value[key], sub_rule) for key, sub_rule in rule.items() if key in value}
    return None


def scrub_orders(orders: list[Any], restaurant_guid: str) -> list[Any]:
    scrubbed: list[Any] = replace_text(scrub(orders, ORDER), restaurant_guid, FAKE_RESTAURANT_GUID)
    return scrubbed


def scrub_menus(body: Any, restaurant_guid: str) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise ToastApiError("Toast menus response is not a JSON object.")
    scrubbed: dict[str, Any] = replace_text(
        scrub(body, MENUS), restaurant_guid, FAKE_RESTAURANT_GUID
    )
    if "restaurantGuid" in scrubbed:
        scrubbed["restaurantGuid"] = FAKE_RESTAURANT_GUID
    return scrubbed


def replace_text(value: Any, old: str, new: str) -> Any:
    """Replace ``old`` with ``new`` in every string inside ``value``."""
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [replace_text(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: replace_text(item, old, new) for key, item in value.items()}
    return value


def find_personal_data(value: Any, path: str = "$") -> list[str]:
    """Where a string looks like an email, card or phone number, as 'path: kind'.

    Only the location and kind are returned, never the value itself, so the result is safe
    to print."""
    if isinstance(value, dict):
        return [
            finding
            for key, item in value.items()
            for finding in find_personal_data(item, f"{path}.{key}")
        ]
    if isinstance(value, list):
        return [
            finding
            for index, item in enumerate(value)
            for finding in find_personal_data(item, f"{path}[{index}]")
        ]
    if not isinstance(value, str):
        return []
    text = GUID.sub("", value)
    return [f"{path}: {kind}" for kind, pattern in PERSONAL_DATA.items() if pattern.search(text)]


def record_days(
    client: ToastClient, first_day: date, days: int, restaurant_guid: str
) -> RecordedDays:
    """Fetch the menu and ``days`` business days of orders, and scrub them."""
    menus = scrub_menus(client.get(MENUS_PATH), restaurant_guid)
    orders_by_day = {
        day: scrub_orders(list(orders_on_business_date(client, day)), restaurant_guid)
        for day in _days(first_day, days)
    }
    return RecordedDays(menus=menus, orders_by_day=orders_by_day)


def to_json(value: Any) -> str:
    """Pretty JSON that keeps prices and quantities as numbers, e.g. 4.2 and 0.35."""
    return json.dumps(value, indent=2, ensure_ascii=False, default=_json_number) + "\n"


def _days(first_day: date, days: int) -> Iterator[date]:
    for offset in range(days):
        yield first_day + timedelta(days=offset)


def _is_plain(value: Any) -> bool:
    return value is None or isinstance(value, str | bool | int | float | Decimal)


def _json_number(value: Any) -> int | float:
    if not isinstance(value, Decimal):
        raise TypeError(f"{type(value).__name__} cannot be saved as JSON.")
    # float() prints the shortest form that reads back the same, so 4.20 is saved as 4.2.
    return int(value) if value == value.to_integral_value() else float(value)
