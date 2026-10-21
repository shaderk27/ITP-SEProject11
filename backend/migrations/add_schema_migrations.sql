-- =============================================================================
-- Migration record: which migration files this database has applied.
-- Non-destructive, idempotent, inserts no demo data. Safe to re-run.
-- Run this FIRST on any existing database.
--
--   PGPASSWORD=postgres psql -v ON_ERROR_STOP=1 -U postgres -h localhost \
--     -d budget_system -f backend/migrations/add_schema_migrations.sql
--   (or paste into pgAdmin's Query Tool on budget_system)
--
-- Show what a database has applied:
--   SELECT * FROM schema_migrations ORDER BY applied_at;
--
-- Convention: migration_name = the file name without ".sql". Every migration
-- file ends by recording itself inside its own transaction, as its very last
-- statement before COMMIT, so a failed migration is never recorded.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name  varchar(255)    PRIMARY KEY,
    applied_at      timestamptz     NOT NULL DEFAULT now(),
    applied_by      text            NOT NULL DEFAULT current_user
);

INSERT INTO schema_migrations (migration_name)
VALUES ('add_schema_migrations')
ON CONFLICT (migration_name) DO NOTHING;

COMMIT;
