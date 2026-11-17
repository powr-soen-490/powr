# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""The menu mapping list: each item's status and how much of the menu is mapped.

- unmapped: no recipe version is in effect now (a version only scheduled for later still
  counts as unmapped).
- needs_review: a recipe is in effect, but it uses an archived ingredient, the item changed in
  the POS since it was saved, or a modifier sold with the item has no lines.
- mapped: a recipe is in effect and nothing needs review.

Coverage counts mapped and needs-review items, by number of items and by revenue over the last
90 days. Unmapped items come first, highest revenue first, so Marco maps what matters most.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.recipes import coverage_repository as repository
from app.modules.recipes.coverage_repository import MenuItemFacts

REVENUE_DAYS = 90
SHARE_STEP = Decimal("0.0001")

Status = Literal["unmapped", "needs_review", "mapped"]
ReviewReason = Literal["inactive_ingredient", "menu_item_changed", "unmapped_modifier"]
STATUS_ORDER: dict[Status, int] = {"unmapped": 0, "needs_review": 1, "mapped": 2}


@dataclass(frozen=True)
class MenuItemStatus:
    facts: MenuItemFacts
    status: Status
    review_reasons: list[ReviewReason]


@dataclass(frozen=True)
class Coverage:
    items_total: int
    items_mapped: int  # mapped or needs review
    revenue_total: Decimal
    revenue_mapped: Decimal

    @property
    def item_share(self) -> Decimal | None:
        return _share(Decimal(self.items_mapped), Decimal(self.items_total))

    @property
    def revenue_share(self) -> Decimal | None:
        return _share(self.revenue_mapped, self.revenue_total)


def classify(facts: MenuItemFacts) -> MenuItemStatus:
    if facts.version_id is None:
        return MenuItemStatus(facts, "unmapped", [])
    reasons: list[ReviewReason] = []
    if facts.inactive_ingredient:
        reasons.append("inactive_ingredient")
    if facts.item_changed:
        reasons.append("menu_item_changed")
    if facts.unmapped_modifiers:
        reasons.append("unmapped_modifier")
    return MenuItemStatus(facts, "needs_review" if reasons else "mapped", reasons)


def summarize(items: list[MenuItemStatus]) -> Coverage:
    mapped = [item for item in items if item.status != "unmapped"]
    return Coverage(
        items_total=len(items),
        items_mapped=len(mapped),
        revenue_total=sum((item.facts.revenue for item in items), Decimal(0)),
        revenue_mapped=sum((item.facts.revenue for item in mapped), Decimal(0)),
    )


def sort_key(item: MenuItemStatus) -> tuple[int, Decimal, str, UUID]:
    """Unmapped first, then needs review, then mapped; highest revenue first in each."""
    return (STATUS_ORDER[item.status], -item.facts.revenue, item.facts.name.lower(), item.facts.id)


def menu_overview(
    db: Session, *, restaurant_id: UUID, now: datetime, status: Status | None = None
) -> tuple[Coverage, list[MenuItemStatus]]:
    """Coverage of the whole menu, and its items (only those with ``status``, when given)."""
    since = (now - timedelta(days=REVENUE_DAYS)).date()
    facts = repository.menu_item_facts(db, restaurant_id=restaurant_id, now=now, since=since)
    items = sorted((classify(f) for f in facts), key=sort_key)
    shown = [item for item in items if status is None or item.status == status]
    return summarize(items), shown


def _share(part: Decimal, total: Decimal) -> Decimal | None:
    return None if total == 0 else (part / total).quantize(SHARE_STEP)
