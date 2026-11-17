-- Source-File AI Declaration
-- AI contribution: 50% or more AI-generated
-- Issue #173: keep the Toast access token between requests, and remember when Toast rejects
-- the saved client ID or secret. Every script in db/ runs again on each migrate, so each
-- statement here only changes what is missing and never touches data that is already saved.

-- True only when Toast rejected the saved client ID or secret; reconnecting clears it.
-- An access token that expires on its own never sets it.
ALTER TABLE pos_credentials
    ADD COLUMN IF NOT EXISTS needs_reconnect BOOLEAN NOT NULL DEFAULT FALSE;

-- expires_at was a TIMESTAMP without a time zone. Nothing ever saved it before this issue,
-- so converting it to UTC-aware TIMESTAMPTZ cannot change any saved value. The check makes
-- the conversion run only once: converting a TIMESTAMPTZ again would shift it by the
-- session's time zone.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'pos_credentials'
          AND column_name = 'expires_at'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE pos_credentials
            ALTER COLUMN expires_at TYPE TIMESTAMPTZ USING expires_at AT TIME ZONE 'UTC';
    END IF;
END
$$;
