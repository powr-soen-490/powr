-- Source-File AI Declaration
-- AI contribution: 50% or more AI-generated
-- Issue #42: record when an invite link is used, so each link works only once.
-- Safe to run again: the column is only added when it is missing.

ALTER TABLE invites ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMP WITH TIME ZONE;
