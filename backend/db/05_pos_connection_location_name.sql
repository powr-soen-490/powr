-- Source-File AI Declaration
-- AI contribution: 50% or more AI-generated
-- The POS location's name, so the settings page can show which restaurant is connected.
-- Nullable: connections saved before this column existed have no name.

ALTER TABLE pos_connections ADD COLUMN IF NOT EXISTS location_name VARCHAR(255);
