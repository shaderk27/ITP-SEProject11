-- =============================================================================
-- Lab IC assignments: many-to-many (replaces users.lab_id AND labs.user_id).
-- Run once on existing DBs (fresh DBs built from db_setup.sql already have it).
-- Safe to re-run. Replaces migrate_lab_ic_to_labs.sql -- do NOT run both.
--
--   PGPASSWORD=postgres psql -U postgres -h localhost -d budget_system \
--     -f migrate_lab_ic_to_assignments.sql
--
-- Works from either starting point:
--   (a) old model:  users.lab_id        (several users could share a lab)
--   (b) 1-1 model:  labs.user_id UNIQUE (from migrate_lab_ic_to_labs.sql)
--
-- Nothing is lost: when several users shared a lab, the lowest user_id becomes
-- the primary Lab IC and the rest become secondary Lab ICs.
--
-- Activation history uses the existing audit_logs table. Convention:
--   user_id     = admin who acted
--   action_type = 'user_deactivated' | 'user_reactivated'
--   entity_name = 'users'
--   record_id   = target user's user_id (as text)
--   old_value / new_value = {"is_active": <bool>}
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

-- 1. users.is_active (some DBs only got it from the seed scripts).
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- 2. Assignment table.
CREATE TABLE IF NOT EXISTS lab_ic_assignments (
    assignment_id   bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lab_id          bigint      NOT NULL REFERENCES labs (lab_id)   ON DELETE CASCADE,
    user_id         bigint      NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    is_primary      boolean     NOT NULL DEFAULT false,
    assigned_at     timestamptz NOT NULL DEFAULT now(),
    assigned_by     bigint      REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT uq_lab_ic_lab_user UNIQUE (lab_id, user_id)
);

-- At most one primary Lab IC per lab.
CREATE UNIQUE INDEX IF NOT EXISTS uq_lab_ic_one_primary
    ON lab_ic_assignments (lab_id) WHERE is_primary;
CREATE INDEX IF NOT EXISTS idx_lic_user_id ON lab_ic_assignments (user_id);

-- Fast lookup of a user's activate/deactivate history.
CREATE INDEX IF NOT EXISTS idx_al_entity_record ON audit_logs (entity_name, record_id);

-- 3. Backfill, then drop whichever old column still exists.
DO $$
DECLARE
  n_labs  integer := 0;
  n_users integer := 0;
BEGIN
  -- (b) 1-1 model: labs.user_id -> primary assignment.
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'labs' AND column_name = 'user_id'
  ) THEN
    INSERT INTO lab_ic_assignments (lab_id, user_id, is_primary)
    SELECT lab_id, user_id, true
    FROM labs
    WHERE user_id IS NOT NULL
    ON CONFLICT (lab_id, user_id) DO NOTHING;
    GET DIAGNOSTICS n_labs = ROW_COUNT;

    ALTER TABLE labs DROP COLUMN user_id;   -- also drops fk_labs_user / uq_labs_user
    RAISE NOTICE 'Migrated % assignment(s) from labs.user_id.', n_labs;
  END IF;

  -- (a) old model: users.lab_id -> primary (lowest user_id) + secondaries.
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'users' AND column_name = 'lab_id'
  ) THEN
    INSERT INTO lab_ic_assignments (lab_id, user_id, is_primary)
    SELECT
      u.lab_id,
      u.user_id,
      NOT EXISTS (
        SELECT 1 FROM lab_ic_assignments a
        WHERE a.lab_id = u.lab_id AND a.is_primary
      ) AND row_number() OVER (PARTITION BY u.lab_id ORDER BY u.user_id) = 1
    FROM users u
    WHERE u.lab_id IS NOT NULL
    ON CONFLICT (lab_id, user_id) DO NOTHING;
    GET DIAGNOSTICS n_users = ROW_COUNT;

    ALTER TABLE users DROP COLUMN lab_id;
    RAISE NOTICE 'Migrated % assignment(s) from users.lab_id.', n_users;
  END IF;
END $$;
INSERT INTO schema_migrations (migration_name)
VALUES ('migrate_lab_ic_to_assignments')
ON CONFLICT (migration_name) DO NOTHING;
COMMIT;
