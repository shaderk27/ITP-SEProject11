-- =============================================================================
-- Source-system PR status on PR Records (Irfan W9-02 / W11-03).
-- Non-destructive, idempotent, inserts no data. Needs
-- add_schema_migrations.sql to have been run.
--
--   PGPASSWORD=postgres psql -U postgres -h localhost -d budget_system \
--     -f backend/migrations/add_pr_status_columns.sql
-- =============================================================================

BEGIN;

ALTER TABLE purchase_requests      ADD COLUMN IF NOT EXISTS pr_status varchar(50);
ALTER TABLE purchase_request_lines ADD COLUMN IF NOT EXISTS pr_status varchar(50);

INSERT INTO schema_migrations (migration_name)
VALUES ('add_pr_status_columns')
ON CONFLICT (migration_name) DO NOTHING;

COMMIT;
