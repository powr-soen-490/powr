-- Source-File AI Declaration
-- AI contribution: 50% or more AI-generated
-- Shared POS provider client credentials. Encrypt client_secret before storing it.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS pos_credentials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pos_name VARCHAR(50) NOT NULL UNIQUE,
    client_id TEXT NOT NULL,
    client_secret TEXT NOT NULL,
    access_token TEXT,
    expires_at TIMESTAMP
);
