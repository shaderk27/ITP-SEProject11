-- =============================================================================
-- Threshold-alert state on labs and lab_groups (Randy W11-02, W13-04), plus
-- labs.lab_group_id nullable (Randy). Non-destructive, idempotent, no data.
-- Needs budget_periods and add_schema_migrations.sql.
--
--   PGPASSWORD=postgres psql -v ON_ERROR_STOP=1 -U postgres -h localhost \
--     -d budget_system -f backend/migrations/add_alert_state_columns.sql
--
-- Aborts (and rolls back) if existing alert_period_id values point at a
-- period that does not exist. Fix or NULL those rows, then re-run.
-- =============================================================================
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['labs', 'lab_groups', 'budget_periods']
  LOOP
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.tables
      WHERE table_schema = current_schema() AND table_name = t
    ) THEN
      RAISE EXCEPTION 'Prerequisite table % does not exist. Run db_setup.sql first.', t;
    END IF;
  END LOOP;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = current_schema() AND table_name = 'schema_migrations'
  ) THEN
    RAISE EXCEPTION 'schema_migrations table does not exist. Run add_schema_migrations.sql first.';
  END IF;
END $$;

BEGIN;

-- labs
ALTER TABLE labs ALTER COLUMN lab_group_id DROP NOT NULL;
ALTER TABLE labs ADD COLUMN IF NOT EXISTS notified_50     boolean DEFAULT false;
ALTER TABLE labs ADD COLUMN IF NOT EXISTS notified_80     boolean DEFAULT false;
ALTER TABLE labs ADD COLUMN IF NOT EXISTS notified_95     boolean DEFAULT false;
ALTER TABLE labs ADD COLUMN IF NOT EXISTS notified_100    boolean DEFAULT false;
ALTER TABLE labs ADD COLUMN IF NOT EXISTS alert_period_id bigint;

-- lab_groups
ALTER TABLE lab_groups ADD COLUMN IF NOT EXISTS notified_50     boolean DEFAULT false;
ALTER TABLE lab_groups ADD COLUMN IF NOT EXISTS notified_80     boolean DEFAULT false;
ALTER TABLE lab_groups ADD COLUMN IF NOT EXISTS notified_95     boolean DEFAULT false;
ALTER TABLE lab_groups ADD COLUMN IF NOT EXISTS notified_100    boolean DEFAULT false;
ALTER TABLE lab_groups ADD COLUMN IF NOT EXISTS alert_period_id bigint;

-- Foreign keys to budget_periods. lab_groups never had one; labs did.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM labs t
    WHERE t.alert_period_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM budget_periods p WHERE p.period_id = t.alert_period_id)
  ) THEN
    RAISE EXCEPTION 'labs.alert_period_id has values with no matching budget_periods row';
  END IF;

  IF EXISTS (
    SELECT 1 FROM lab_groups t
    WHERE t.alert_period_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM budget_periods p WHERE p.period_id = t.alert_period_id)
  ) THEN
    RAISE EXCEPTION 'lab_groups.alert_period_id has values with no matching budget_periods row';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'fk_labs_alert_period' AND conrelid = 'labs'::regclass
  ) THEN
    ALTER TABLE labs ADD CONSTRAINT fk_labs_alert_period
      FOREIGN KEY (alert_period_id) REFERENCES budget_periods (period_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'fk_lab_groups_alert_period' AND conrelid = 'lab_groups'::regclass
  ) THEN
    ALTER TABLE lab_groups ADD CONSTRAINT fk_lab_groups_alert_period
      FOREIGN KEY (alert_period_id) REFERENCES budget_periods (period_id);
  END IF;
END $$;

-- Record the migration last, after every schema change above has succeeded.
INSERT INTO schema_migrations (migration_name)
VALUES ('add_alert_state_columns')
ON CONFLICT (migration_name) DO NOTHING;

COMMIT;
