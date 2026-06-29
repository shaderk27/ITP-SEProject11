-- W7-02/03 local auth seed.
-- Keep this aligned with backend/seeds/dev_seed.sql. It must not create a
-- second set of lab groups/labs with older WBS aliases.

ALTER TABLE labs ALTER COLUMN lab_group_id DROP NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS lab_id BIGINT REFERENCES labs(lab_id);
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

-- Demo users. Password hashes are placeholders unless replaced by auth setup.
INSERT INTO users (
  role_id,
  full_name,
  email,
  staff_id,
  password_hash,
  lab_group_id,
  lab_id,
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
    NULL,
    TRUE
  ),
  (
    (SELECT role_id FROM roles WHERE role_name = 'labic'),
    'Development Lab IC',
    'labic.fcb@example.com',
    'DEV-LIC-FCB',
    'placeholder_no_auth_yet',
    NULL,
    (SELECT lab_id FROM labs WHERE lab_code = 'W3-01-021'),
    TRUE
  ),
  (
    (SELECT role_id FROM roles WHERE role_name = 'labic'),
    'ICT Lab IC',
    'labic.ict@example.com',
    'DEV-LIC-ICT',
    'placeholder_no_auth_yet',
    NULL,
    (SELECT lab_id FROM labs WHERE lab_code = 'E2-02-02'),
    TRUE
  ),
  (
    (SELECT role_id FROM roles WHERE role_name = 'labic'),
    'Unassigned Lab IC',
    'labic.non@example.com',
    'DEV-LIC-NON',
    'placeholder_no_auth_yet',
    NULL,
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
    NULL,
    TRUE
  )
ON CONFLICT (email) DO UPDATE
SET
  role_id = EXCLUDED.role_id,
  full_name = EXCLUDED.full_name,
  staff_id = EXCLUDED.staff_id,
  password_hash = EXCLUDED.password_hash,
  lab_group_id = EXCLUDED.lab_group_id,
  lab_id = EXCLUDED.lab_id,
  is_active = EXCLUDED.is_active;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
SELECT setval(pg_get_serial_sequence('roles', 'role_id'), (SELECT MAX(role_id) FROM roles));
SELECT setval(pg_get_serial_sequence('lab_groups', 'lab_group_id'), (SELECT MAX(lab_group_id) FROM lab_groups));
SELECT setval(pg_get_serial_sequence('labs', 'lab_id'), (SELECT MAX(lab_id) FROM labs));
SELECT setval(pg_get_serial_sequence('users', 'user_id'), (SELECT MAX(user_id) FROM users));
DROP TABLE IF EXISTS password_reset_tokens            CASCADE;
CREATE TABLE password_reset_tokens (
    token_id        bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         bigint          NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    temp_password   text            NOT NULL,       -- hashed
    expires_at      timestamptz     NOT NULL,
    used            boolean         NOT NULL DEFAULT false,
    created_at      timestamptz     NOT NULL DEFAULT now()
);