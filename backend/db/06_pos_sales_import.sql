-- Source-File AI Declaration
-- AI contribution: 50% or more AI-generated
-- Imported POS menus and sales, and the background jobs that import them (issue #53).
-- Every script in db/ runs again on each migrate, so each statement here only creates what
-- is missing and never touches data that is already saved.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- The unused placeholder order tables that 01_init.sql used to create. The new tables have
-- different names, so these drops can never hit imported sales when this script runs again.
DROP TABLE IF EXISTS pos_order_line_items;
DROP TABLE IF EXISTS pos_orders;

-- Menu items, one row per POS item. Items the POS no longer lists, and items only seen in
-- old sales, are kept with is_active = false, never deleted, so their sales keep a name.
CREATE TABLE IF NOT EXISTS menu_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    pos_item_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    price NUMERIC(10, 2),  -- null when the POS has no single price, e.g. priced by size
    currency CHAR(3) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_mock BOOLEAN NOT NULL DEFAULT false,  -- generated test data, safe to delete
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (restaurant_id, provider, pos_item_id)
);

-- Modifier options ("Extra feta", "Side: rice"), one row per option, with the name of the
-- group it was first seen in ("Add-ons"). Sales point to options by pos_modifier_id.
CREATE TABLE IF NOT EXISTS menu_modifiers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    pos_modifier_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    group_name VARCHAR(255) NOT NULL,
    price NUMERIC(10, 2),
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_mock BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (restaurant_id, provider, pos_modifier_id)
);

-- One row per POS order. The unique key is what makes re-running an import update orders
-- instead of saving them twice.
CREATE TABLE IF NOT EXISTS sales_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    pos_order_id VARCHAR(255) NOT NULL,
    business_date DATE NOT NULL,  -- the restaurant's day: a 1am sale belongs to the night before
    opened_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_mock BOOLEAN NOT NULL DEFAULT false,  -- generated test data; its lines go with it
    imported_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (restaurant_id, provider, pos_order_id),
    UNIQUE (id, restaurant_id)  -- lets lines check they belong to the same restaurant
);

-- One row per item sold. Voided lines are kept with is_voided = true so a later void can be
-- applied; forecasts and totals ignore them. Refunded items count as sold, since the food
-- was still made.
CREATE TABLE IF NOT EXISTS sales_order_lines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    sales_order_id UUID NOT NULL,
    pos_line_id VARCHAR(255) NOT NULL,
    pos_item_id VARCHAR(255) NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    quantity NUMERIC(12, 4) NOT NULL CHECK (quantity > 0),  -- can be a weight, e.g. 0.35 lb
    price NUMERIC(10, 2),  -- the line total, after discounts
    business_date DATE NOT NULL,  -- copied from the order, so item-by-day queries skip a join
    -- [{"pos_item_id": "...", "name": "Extra feta", "quantity": "2"}], quantities as strings
    -- so they stay exact
    modifiers JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_voided BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (sales_order_id, pos_line_id),
    -- A line can only belong to an order of the same restaurant.
    FOREIGN KEY (sales_order_id, restaurant_id)
        REFERENCES sales_orders (id, restaurant_id) ON DELETE CASCADE
);

-- Background imports. last_completed_date is the bookmark: every day up to it is saved, so
-- a retry continues from the day after.
CREATE TABLE IF NOT EXISTS sync_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'failed', 'done')),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    last_completed_date DATE,
    orders_imported INTEGER NOT NULL DEFAULT 0,
    items_imported INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITH TIME ZONE,
    CHECK (start_date <= end_date),
    CHECK (last_completed_date IS NULL OR last_completed_date BETWEEN start_date AND end_date)
);

-- Sales of one item by day, for forecasting (the "sales by item and date" index from #57).
CREATE INDEX IF NOT EXISTS idx_sales_order_lines_item_date
    ON sales_order_lines (restaurant_id, pos_item_id, business_date);
CREATE INDEX IF NOT EXISTS idx_sales_order_lines_order ON sales_order_lines (sales_order_id);
CREATE INDEX IF NOT EXISTS idx_sales_orders_date ON sales_orders (restaurant_id, business_date);
-- Only one running import per restaurant and POS; finished and failed jobs don't count.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_jobs_one_running
    ON sync_jobs (restaurant_id, provider) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS idx_sync_jobs_latest
    ON sync_jobs (restaurant_id, provider, created_at DESC);
