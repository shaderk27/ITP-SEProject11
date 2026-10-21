-- =============================================================================
-- W7-02/03 local auth seed.
-- Keep this aligned with backend/seeds/dev_seed.sql. It must not create a
-- second set of lab groups/labs with older WBS aliases.
--
-- Safe to re-run. All-or-nothing: runs in one transaction, and stops at the
-- first error. Needs db_setup.sql (or the migrations, including
-- migrate_lab_ic_to_assignments.sql) to have been run first.
--
-- Re-running does NOT overwrite password_hash on existing users, so passwords
-- set by real auth setup survive. New users get the placeholder hash.
--
--   PGPASSWORD=postgres psql -v ON_ERROR_STOP=1 -U postgres -h localhost \
--     -d budget_system -f backend/seeds/w7_auth_seed.sql
-- =============================================================================

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'roles', 'lab_groups', 'labs', 'users', 'lab_ic_assignments'
  ]
  LOOP
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.tables
      WHERE table_schema = current_schema() AND table_name = t
    ) THEN
      RAISE EXCEPTION 'Prerequisite table % does not exist. Run db_setup.sql first (older DBs: migrate_lab_ic_to_assignments.sql).', t;
    END IF;
  END LOOP;
END $$;

BEGIN;

ALTER TABLE labs ALTER COLUMN lab_group_id DROP NOT NULL;
-- Lab IC assignments live in lab_ic_assignments (many-to-many). Fresh DBs get
-- it from db_setup.sql; older DBs: run migrate_lab_ic_to_assignments.sql once.
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Roles.
INSERT INTO roles (role_name)
VALUES
  ('admin'),
  ('teamlead'),
  ('labic')
ON CONFLICT (role_name) DO NOTHING;

-- Canonical lab groups used by upload classification and review scoping.
INSERT INTO lab_groups (lab_group_name, wbs_code, description)
SELECT 'General', 'GENERAL', 'Fallback group for spending without a confident lab-group match'
WHERE NOT EXISTS (SELECT 1 FROM lab_groups WHERE lab_group_name = 'General');

INSERT INTO lab_groups (lab_group_name, wbs_code, description)
SELECT 'FCB', 'WBS-FCB-001', 'Food, Chemistry and Biology'
WHERE NOT EXISTS (SELECT 1 FROM lab_groups WHERE lab_group_name = 'FCB');

INSERT INTO lab_groups (lab_group_name, wbs_code, description)
SELECT 'ICT', 'WBS-ICT-002', 'Information and Communication Technology'
WHERE NOT EXISTS (SELECT 1 FROM lab_groups WHERE lab_group_name = 'ICT');

-- Per-group General lab fallback.
INSERT INTO labs (lab_group_id, lab_code, lab_name, is_general)
SELECT
  lg.lab_group_id,
  'GEN-' || lg.lab_group_name,
  'General',
  true
FROM lab_groups lg
WHERE NOT EXISTS (
  SELECT 1 FROM labs l
  WHERE l.lab_group_id = lg.lab_group_id
    AND l.is_general = true
);

-- Demo concrete labs used by current samples.
INSERT INTO labs (lab_group_id, lab_code, lab_name, is_general)
SELECT
  (SELECT lab_group_id FROM lab_groups WHERE lab_group_name = 'ICT'),
  'E2-02-02',
  'ICT Embedded Lab',
  false
WHERE NOT EXISTS (SELECT 1 FROM labs WHERE lab_code = 'E2-02-02');

INSERT INTO labs (lab_group_id, lab_code, lab_name, is_general)
SELECT
  (SELECT lab_group_id FROM lab_groups WHERE lab_group_name = 'FCB'),
  'W3-01-021',
  'W3 Food Processing Lab',
  false
WHERE NOT EXISTS (SELECT 1 FROM labs WHERE lab_code = 'W3-01-021');

-- Demo users. New users get a placeholder password_hash; existing users keep
-- whatever hash they already have.
INSERT INTO users (
  role_id,
  full_name,
  email,
  staff_id,
  password_hash,
  lab_group_id,
  is_active
)
VALUES
  (
    (SELECT role_id FROM roles WHERE role_name = 'admin'),
    'Development Admin',
    'admin@example.com',
    'DEV-ADMIN',
    'placeholder_no_auth_yet',
    NULL,
    TRUE
  ),
  (
    (SELECT role_id FROM roles WHERE role_name = 'teamlead'),
    'Development Team Lead',
    'teamlead.fcb@example.com',
    'DEV-TL-FCB',
    'placeholder_no_auth_yet',
    (SELECT lab_group_id FROM lab_groups WHERE lab_group_name = 'FCB'),
    TRUE
  ),
  (
    (SELECT role_id FROM roles WHERE role_name = 'labic'),
    'Development Lab IC',
    'labic.fcb@example.com',
    'DEV-LIC-FCB',
    'placeholder_no_auth_yet',
    NULL,
    TRUE
  ),
  (
    (SELECT role_id FROM roles WHERE role_name = 'labic'),
    'ICT Lab IC',
    'labic.ict@example.com',
    'DEV-LIC-ICT',
    'placeholder_no_auth_yet',
    NULL,
    TRUE
  ),
  (
    (SELECT role_id FROM roles WHERE role_name = 'labic'),
    'Unassigned Lab IC',
    'labic.non@example.com',
    'DEV-LIC-NON',
    'placeholder_no_auth_yet',
    NULL,
    TRUE
  ),
  (
    (SELECT role_id FROM roles WHERE role_name = 'teamlead'),
    'Unassigned Team Lead',
    'teamlead.non@example.com',
    'DEV-TL-NON',
    'placeholder_no_auth_yet',
    NULL,
    TRUE
  )
ON CONFLICT (email) DO UPDATE
SET
  role_id = EXCLUDED.role_id,
  full_name = EXCLUDED.full_name,
  staff_id = EXCLUDED.staff_id,
  lab_group_id = EXCLUDED.lab_group_id,
  is_active = EXCLUDED.is_active;

-- Lab IC assignments (lab_ic_assignments). Idempotent: existing rows are left
-- alone and a demo IC becomes primary only if the lab has no primary yet.
-- labic.non stays unassigned.
INSERT INTO lab_ic_assignments (lab_id, user_id, is_primary)
SELECT
  l.lab_id,
  u.user_id,
  NOT EXISTS (
    SELECT 1 FROM lab_ic_assignments a WHERE a.lab_id = l.lab_id AND a.is_primary
  )
FROM (VALUES
  ('W3-01-021', 'labic.fcb@example.com'),
  ('E2-02-02',  'labic.ict@example.com')
) AS m(lab_code, email)
JOIN labs  l ON l.lab_code = m.lab_code
JOIN users u ON u.email = m.email
ON CONFLICT (lab_id, user_id) DO NOTHING;

-- Keep identity sequences ahead of the seeded rows.
SELECT setval(pg_get_serial_sequence('roles', 'role_id'), (SELECT MAX(role_id) FROM roles));
SELECT setval(pg_get_serial_sequence('lab_groups', 'lab_group_id'), (SELECT MAX(lab_group_id) FROM lab_groups));
SELECT setval(pg_get_serial_sequence('labs', 'lab_id'), (SELECT MAX(lab_id) FROM labs));
SELECT setval(pg_get_serial_sequence('users', 'user_id'), (SELECT MAX(user_id) FROM users));

COMMIT;
