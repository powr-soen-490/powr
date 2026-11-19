# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""Menu item statuses and coverage without a database."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.modules.recipes.coverage_repository import MenuItemFacts
from app.modules.recipes.coverage_service import classify, summarize


def facts(*, mapped: bool = True, revenue: str = "0", **signals: Any) -> MenuItemFacts:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "Souvlaki plate",
        "price": Decimal("18.50"),
        "is_active": True,
        "revenue": Decimal(revenue),
        "version_id": uuid.uuid4() if mapped else None,
        "effective_from": datetime(2026, 11, 1, tzinfo=UTC) if mapped else None,
        "item_changed": False,
        "inactive_ingredient": False,
        "unmapped_modifiers": [],
    }
    return MenuItemFacts(**{**values, **signals})


def test_status_and_review_reasons() -> None:
    assert classify(facts(mapped=False)).status == "unmapped"
    assert classify(facts()).status == "mapped"
    review = classify(
        facts(inactive_ingredient=True, item_changed=True, unmapped_modifiers=["Add tzatziki"])
    )
    assert review.status == "needs_review"
    assert review.review_reasons == [
        "inactive_ingredient",
        "menu_item_changed",
        "unmapped_modifier",
    ]


def test_coverage_counts_items_with_a_recipe_by_number_and_revenue() -> None:
    items = [
        classify(facts(revenue="100")),
        classify(facts(revenue="20", item_changed=True)),
        classify(facts(mapped=False, revenue="80")),
    ]
    coverage = summarize(items)
    assert (coverage.items_mapped, coverage.items_total) == (2, 3)
    assert coverage.item_share == Decimal("0.6667")
    assert coverage.revenue_share == Decimal("0.6")


def test_no_items_or_revenue_has_no_share() -> None:
    coverage = summarize([])
    assert (coverage.item_share, coverage.revenue_share) == (None, None)
