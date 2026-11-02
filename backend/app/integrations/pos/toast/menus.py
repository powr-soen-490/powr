# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Translates Toast menus v2 responses into MenuItem models."""

from collections.abc import Iterator
from typing import Any

from app.integrations.pos.models import (
    MenuItem,
    MenuModifierGroup,
    MenuModifierOption,
    PosConnection,
)
from app.integrations.pos.toast.client import ToastApiError

# Standard API access can read menus v2 only; v3 answers 403.
MENUS_PATH = "/menus/v2/menus"
MISSING_NAME = "Missing name"


def menu_items_from_toast(body: Any, connection: PosConnection, currency: str) -> list[MenuItem]:
    """One MenuItem per Toast item GUID, in menu order; an item on several menus keeps the
    first price found."""
    if not isinstance(body, dict):
        raise ToastApiError("Toast menus response is not a JSON object.")
    group_references: dict[str, Any] = body.get("modifierGroupReferences") or {}
    option_references: dict[str, Any] = body.get("modifierOptionReferences") or {}

    items: dict[str, MenuItem] = {}
    for toast_item in _menu_items(body.get("menus") or []):
        guid = toast_item.get("guid")
        if not guid or guid in items:
            continue
        items[guid] = MenuItem(
            connection_id=connection.id,
            restaurant_id=connection.restaurant_id,
            item_id=guid,
            item_name=toast_item.get("name") or MISSING_NAME,
            price=toast_item.get("price"),
            currency=currency,
            modifier_groups=tuple(
                _modifier_groups(
                    toast_item.get("modifierGroupReferences") or [],
                    group_references,
                    option_references,
                )
            ),
        )
    return list(items.values())


def _menu_items(menus: list[Any]) -> Iterator[dict[str, Any]]:
    for menu in menus:
        yield from _items_in_groups(menu.get("menuGroups") or [])


def _items_in_groups(groups: list[Any]) -> Iterator[dict[str, Any]]:
    """Menu groups can contain more menu groups, so walk them recursively."""
    for group in groups:
        yield from group.get("menuItems") or []
        yield from _items_in_groups(group.get("menuGroups") or [])


def _modifier_groups(
    reference_ids: list[int],
    group_references: dict[str, Any],
    option_references: dict[str, Any],
) -> Iterator[MenuModifierGroup]:
    for reference_id in reference_ids:
        # JSON object keys are always strings, so referenceId 3 is stored under "3".
        group = group_references.get(str(reference_id))
        if group is None or not group.get("guid"):
            continue
        yield MenuModifierGroup(
            group_id=group["guid"],
            group_name=group.get("name") or MISSING_NAME,
            min_selections=group.get("minSelections") or 0,
            max_selections=group.get("maxSelections"),
            options=tuple(
                _modifier_options(group.get("modifierOptionReferences") or [], option_references)
            ),
        )


def _modifier_options(
    reference_ids: list[int], option_references: dict[str, Any]
) -> Iterator[MenuModifierOption]:
    for reference_id in reference_ids:
        option = option_references.get(str(reference_id))
        if option is None or not option.get("guid"):
            continue
        yield MenuModifierOption(
            option_id=option["guid"],
            option_name=option.get("name") or MISSING_NAME,
            price=option.get("price"),
        )
