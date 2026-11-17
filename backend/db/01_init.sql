-- Source-File AI Declaration
-- AI contribution: 50% or more AI-generated
-- init db setup, subject to change

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Restaurants & Integrations
CREATE TABLE IF NOT EXISTS restaurants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pos_integrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    last_sync_timestamp TIMESTAMP WITH TIME ZONE,
    sync_status VARCHAR(50) DEFAULT 'HEALTHY'
);

-- 2. Vendors & Ingredients
CREATE TABLE IF NOT EXISTS vendors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    contact_email VARCHAR(255),
    order_minimum_amount NUMERIC(10, 2),
    lead_time_days INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ingredients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    vendor_id UUID REFERENCES vendors(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    pack_size_quantity NUMERIC(10, 2),
    pack_unit VARCHAR(50),
    unit_cost NUMERIC(10, 2),
    current_stock_on_hand NUMERIC(10, 2) DEFAULT 0,
    safety_stock_ratio NUMERIC(5, 2) DEFAULT 0.10
);
