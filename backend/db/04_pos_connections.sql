-- Source-File AI Declaration
-- AI contribution: 50% or more AI-generated
-- POS provider connections: links restaurants to their POS locations

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS pos_connections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    location_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(restaurant_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_pos_connections_restaurant ON pos_connections(restaurant_id);
