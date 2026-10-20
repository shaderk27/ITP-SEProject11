-- =============================================================================
-- password_reset_tokens (restores the deleted add_password_reset_tokens.sql).
-- Non-destructive, idempotent, inserts no data. Needs users to exist and
-- add_schema_migrations.sql to have been run.
--
--   PGPASSWORD=postgres psql -U postgres -h localhost -d budget_system \
--     -f backend/migrations/add_password_reset_tokens.sql
--
-- Ends in the same shape as db_setup.sql: temp_password and expires_at have NO
-- default (the backfill defaults below are dropped again), so fresh and
-- migrated databases match.
-- =============================================================================
DO $$
BEGIN
    -- 1. Ensure the schema_migrations table exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = current_schema() 
          AND table_name = 'schema_migrations'
    ) THEN
        RAISE NOTICE 'schema_migrations table does not exist yet. Please run add_schema_migrations.sql first.';
    END IF;

END $$;


BEGIN;

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_id        bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         bigint          NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    temp_password   text            NOT NULL,
    expires_at      timestamptz     NOT NULL,
    used            boolean         NOT NULL DEFAULT false,
    created_at      timestamptz     NOT NULL DEFAULT now()
);

-- Older local tables may be missing columns. The temporary defaults let the
-- ADD COLUMN succeed on tables that already hold rows; such legacy rows get
-- expires_at = now(), so they are already expired and unusable.
ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS temp_password text        NOT NULL DEFAULT '';
ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS expires_at    timestamptz NOT NULL DEFAULT now();
ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS used          boolean     NOT NULL DEFAULT false;
ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS created_at    timestamptz NOT NULL DEFAULT now();

-- Remove the backfill defaults so the final schema matches a fresh setup.
ALTER TABLE password_reset_tokens ALTER COLUMN temp_password DROP DEFAULT;
ALTER TABLE password_reset_tokens ALTER COLUMN expires_at    DROP DEFAULT;

-- FK column index (db_setup.sql indexes every FK column).
CREATE INDEX IF NOT EXISTS idx_prt_user_id ON password_reset_tokens (user_id);

INSERT INTO schema_migrations (migration_name)
VALUES ('add_password_reset_tokens')
ON CONFLICT (migration_name) DO NOTHING;

COMMIT;
