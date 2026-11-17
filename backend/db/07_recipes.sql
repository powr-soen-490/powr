-- Source-File AI Declaration
-- AI contribution: 50% or more AI-generated
-- Recipes: which ingredients each POS menu item uses, and how modifiers change that (#61).
-- Every script in db/ runs again on each migrate, so each statement here only creates what
-- is missing and never touches data that is already saved.
-- Undo with: python -m app.core.database down (from backend/)

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Ingredients get a kind and a base unit. Recipe quantities are stored in the base unit
-- (g, ml or each); app/core/units.py converts whatever unit Marco types into it.
-- The table was unused before this script, so existing rows (none expected) default to count.
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS kind VARCHAR(10) NOT NULL DEFAULT 'count';
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS base_unit VARCHAR(10) NOT NULL DEFAULT 'each';
ALTER TABLE ingredients ALTER COLUMN kind DROP DEFAULT;
ALTER TABLE ingredients ALTER COLUMN base_unit DROP DEFAULT;
-- What the vendor sells: a pack of pack_size base units for pack_price. The cost of one base
-- unit is pack_price / pack_size, worked out when needed, never stored.
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS pack_size NUMERIC(12, 4);
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS pack_price NUMERIC(10, 2);
-- Ingredients are archived, never deleted, so old recipe versions keep pointing at them.
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
    NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
    NOT NULL DEFAULT CURRENT_TIMESTAMP;
-- Replaced by pack_size and pack_price above; never used by any code.
ALTER TABLE ingredients DROP COLUMN IF EXISTS pack_size_quantity;
ALTER TABLE ingredients DROP COLUMN IF EXISTS pack_unit;
ALTER TABLE ingredients DROP COLUMN IF EXISTS unit_cost;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_ingredients_kind_unit') THEN
        ALTER TABLE ingredients ADD CONSTRAINT ck_ingredients_kind_unit CHECK (
            (kind = 'mass' AND base_unit = 'g')
            OR (kind = 'volume' AND base_unit = 'ml')
            OR (kind = 'count' AND base_unit = 'each')
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_ingredients_pack') THEN
        ALTER TABLE ingredients ADD CONSTRAINT ck_ingredients_pack CHECK (
            (pack_size IS NULL OR pack_size > 0) AND (pack_price IS NULL OR pack_price >= 0)
        );
    END IF;
END $$;

-- One ingredient per name, regardless of capitals ("Feta" and "feta" are the same).
CREATE UNIQUE INDEX IF NOT EXISTS uq_ingredients_name
    ON ingredients (restaurant_id, lower(name));
-- Let the tables below check that what they point at belongs to the same restaurant.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ingredients_id_restaurant ON ingredients (id, restaurant_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_vendors_id_restaurant ON vendors (id, restaurant_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_menu_items_id_restaurant ON menu_items (id, restaurant_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_menu_modifiers_id_restaurant
    ON menu_modifiers (id, restaurant_id);

-- 2. One recipe per menu item; its content lives in versions.
CREATE TABLE IF NOT EXISTS recipes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    menu_item_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (restaurant_id, menu_item_id),
    UNIQUE (id, restaurant_id),
    FOREIGN KEY (menu_item_id, restaurant_id)
        REFERENCES menu_items (id, restaurant_id) ON DELETE CASCADE
);

-- A version is in effect from effective_from until the next version's effective_from. A sale
-- uses the version in effect when its order was opened, so editing a recipe never changes
-- the ingredients worked out for past sales. The menu item's name and price are copied in,
-- so a later change in the POS can be flagged for review.
CREATE TABLE IF NOT EXISTS recipe_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    recipe_id UUID NOT NULL,
    effective_from TIMESTAMP WITH TIME ZONE NOT NULL,
    menu_item_name VARCHAR(255) NOT NULL,
    menu_item_price NUMERIC(10, 2),
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (recipe_id, effective_from),
    UNIQUE (id, restaurant_id),
    FOREIGN KEY (recipe_id, restaurant_id)
        REFERENCES recipes (id, restaurant_id) ON DELETE CASCADE
);

-- One ingredient of the base dish. quantity is in the ingredient's base unit; what Marco
-- typed (entered_quantity, entered_unit) is kept to show it back in the editor.
CREATE TABLE IF NOT EXISTS recipe_lines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    recipe_version_id UUID NOT NULL,
    ingredient_id UUID NOT NULL,
    quantity NUMERIC(12, 4) NOT NULL CHECK (quantity > 0),
    entered_quantity NUMERIC(12, 4) NOT NULL CHECK (entered_quantity > 0),
    entered_unit VARCHAR(10) NOT NULL,
    UNIQUE (recipe_version_id, ingredient_id),
    FOREIGN KEY (recipe_version_id, restaurant_id)
        REFERENCES recipe_versions (id, restaurant_id) ON DELETE CASCADE,
    FOREIGN KEY (ingredient_id, restaurant_id) REFERENCES ingredients (id, restaurant_id)
);

-- What a POS modifier does to this dish: "Extra feta" adds 30 g of feta; "Rice instead of
-- pita" is two lines, one removing the pita and one adding the rice.
CREATE TABLE IF NOT EXISTS recipe_modifier_lines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    recipe_version_id UUID NOT NULL,
    menu_modifier_id UUID NOT NULL,
    ingredient_id UUID NOT NULL,
    effect VARCHAR(10) NOT NULL CHECK (effect IN ('add', 'remove')),
    quantity NUMERIC(12, 4) NOT NULL CHECK (quantity > 0),
    entered_quantity NUMERIC(12, 4) NOT NULL CHECK (entered_quantity > 0),
    entered_unit VARCHAR(10) NOT NULL,
    UNIQUE (recipe_version_id, menu_modifier_id, ingredient_id),
    FOREIGN KEY (recipe_version_id, restaurant_id)
        REFERENCES recipe_versions (id, restaurant_id) ON DELETE CASCADE,
    FOREIGN KEY (menu_modifier_id, restaurant_id)
        REFERENCES menu_modifiers (id, restaurant_id) ON DELETE CASCADE,
    FOREIGN KEY (ingredient_id, restaurant_id) REFERENCES ingredients (id, restaurant_id)
);

CREATE INDEX IF NOT EXISTS idx_recipe_versions_restaurant ON recipe_versions (restaurant_id);
CREATE INDEX IF NOT EXISTS idx_recipe_lines_ingredient ON recipe_lines (ingredient_id);
CREATE INDEX IF NOT EXISTS idx_recipe_modifier_lines_version
    ON recipe_modifier_lines (recipe_version_id);
CREATE INDEX IF NOT EXISTS idx_ingredients_restaurant ON ingredients (restaurant_id);
