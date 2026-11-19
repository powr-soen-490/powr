# Source-File AI Declaration
# AI contribution: 50% or more AI-generated
"""The facts behind the menu mapping list: each item's recent revenue, its recipe version in
effect, and the signs that the recipe needs review. Read-only.

Same sales rule as the rest of powr: voided lines and generated (mock) data are left out,
refunded lines count as sold.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class MenuItemFacts:
    id: UUID
    name: str
    price: Decimal | None
    is_active: bool
    revenue: Decimal  # since the given date
    version_id: UUID | None  # the recipe version in effect now, if any
    effective_from: datetime | None
    item_changed: bool  # renamed, repriced or deactivated in the POS since the version
    inactive_ingredient: bool  # the version uses an archived ingredient
    unmapped_modifiers: list[str]  # sold with the item since the given date, without lines


def menu_item_facts(
    db: Session, *, restaurant_id: UUID, now: datetime, since: date
) -> list[MenuItemFacts]:
    """Active items, plus inactive ones that have a recipe or sold since ``since``."""
    rows = db.execute(
        _MENU_ITEM_FACTS, {"restaurant_id": restaurant_id, "now": now, "since": since}
    )
    return [MenuItemFacts(**row._asdict()) for row in rows]


_MENU_ITEM_FACTS = text("""
    WITH sold AS (
        SELECT o.provider, line.pos_item_id, line.price, line.modifiers
        FROM sales_order_lines AS line
        JOIN sales_orders AS o
          ON o.id = line.sales_order_id AND o.restaurant_id = line.restaurant_id
        WHERE line.restaurant_id = :restaurant_id AND line.business_date >= :since
          AND NOT line.is_voided AND NOT o.is_mock
    ),
    revenue AS (
        SELECT provider, pos_item_id, coalesce(sum(price), 0) AS revenue
        FROM sold GROUP BY provider, pos_item_id
    ),
    sold_modifiers AS (
        SELECT DISTINCT sold.provider, sold.pos_item_id, m ->> 'pos_item_id' AS pos_modifier_id
        FROM sold, jsonb_array_elements(sold.modifiers) AS m
    ),
    current_version AS (
        SELECT DISTINCT ON (r.menu_item_id)
               r.menu_item_id, v.id, v.effective_from, v.menu_item_name, v.menu_item_price
        FROM recipes AS r
        JOIN recipe_versions AS v ON v.recipe_id = r.id AND v.restaurant_id = r.restaurant_id
        WHERE r.restaurant_id = :restaurant_id AND v.effective_from <= :now
        ORDER BY r.menu_item_id, v.effective_from DESC
    )
    SELECT mi.id, mi.name, mi.price, mi.is_active,
           coalesce(rev.revenue, 0) AS revenue,
           cv.id AS version_id, cv.effective_from,
           coalesce(
               mi.name <> cv.menu_item_name
               OR mi.price IS DISTINCT FROM cv.menu_item_price
               OR NOT mi.is_active,
               false
           ) AS item_changed,
           EXISTS (
               SELECT 1 FROM recipe_lines AS l
               JOIN ingredients AS i ON i.id = l.ingredient_id
               WHERE l.recipe_version_id = cv.id AND NOT i.is_active
               UNION ALL
               SELECT 1 FROM recipe_modifier_lines AS l
               JOIN ingredients AS i ON i.id = l.ingredient_id
               WHERE l.recipe_version_id = cv.id AND NOT i.is_active
           ) AS inactive_ingredient,
           ARRAY(
               SELECT mm.name
               FROM sold_modifiers AS s
               JOIN menu_modifiers AS mm
                 ON mm.restaurant_id = :restaurant_id AND mm.provider = s.provider
                AND mm.pos_modifier_id = s.pos_modifier_id
               WHERE cv.id IS NOT NULL
                 AND s.provider = mi.provider AND s.pos_item_id = mi.pos_item_id
                 AND NOT EXISTS (
                     SELECT 1 FROM recipe_modifier_lines AS ml
                     WHERE ml.recipe_version_id = cv.id AND ml.menu_modifier_id = mm.id
                 )
               ORDER BY lower(mm.name)
           ) AS unmapped_modifiers
    FROM menu_items AS mi
    LEFT JOIN revenue AS rev ON rev.provider = mi.provider AND rev.pos_item_id = mi.pos_item_id
    LEFT JOIN current_version AS cv ON cv.menu_item_id = mi.id
    WHERE mi.restaurant_id = :restaurant_id AND NOT mi.is_mock
      AND (mi.is_active OR cv.id IS NOT NULL OR rev.revenue IS NOT NULL)
""")
