-- =============================================================================
-- Move Lab IC ownership from users.lab_id to labs.user_id (1-1).
-- Run once on existing DBs (fresh DBs built from db_setup.sql already have it).
-- Safe to re-run.
--
--   PGPASSWORD=postgres psql -U postgres -h localhost -d budget_system \
--     -f migrate_lab_ic_to_labs.sql
-- =============================================================================

BEGIN;

-- 1. New column. Drop-then-add so the constraints are always in the expected shape.
ALTER TABLE labs ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE labs DROP CONSTRAINT IF EXISTS fk_labs_user;
ALTER TABLE labs DROP CONSTRAINT IF EXISTS uq_labs_user;

-- 2. Copy existing assignments across, then drop the old column.
--    Only runs if users.lab_id still exists. The old model let several users share
--    one lab; labs.user_id can hold one, so the lowest user_id is kept per lab and
--    the others are reported and left unassigned.
DO $$
DECLARE
  dropped integer;
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'users' AND column_name = 'lab_id'
  ) THEN
    UPDATE labs l
    SET user_id = src.user_id
    FROM (
      SELECT DISTINCT ON (lab_id) lab_id, user_id
      FROM users
      WHERE lab_id IS NOT NULL
      ORDER BY lab_id, user_id
    ) src
    WHERE l.lab_id = src.lab_id
      AND l.user_id IS NULL;

    SELECT count(*) INTO dropped
    FROM users u
    WHERE u.lab_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM labs l WHERE l.user_id = u.user_id);

    IF dropped > 0 THEN
      RAISE NOTICE '% user(s) shared a lab with another user and are now unassigned.', dropped;
    END IF;

    ALTER TABLE users DROP COLUMN lab_id;
  END IF;
END $$;

-- 3. Enforce the 1-1 relation.
ALTER TABLE labs
  ADD CONSTRAINT fk_labs_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE SET NULL,
  ADD CONSTRAINT uq_labs_user UNIQUE (user_id);

COMMIT;
