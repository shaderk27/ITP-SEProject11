-- ===========================================================
-- Dev seed for Lab Budget Monitoring System
-- Safe to re-run: every insert checks for existence first.
-- Run from project root:
--   PGPASSWORD=postgres psql -U postgres -h localhost -d budget_system \
--     -f backend/seeds/dev_seed.sql
-- ===========================================================


-- ----- 1. Roles -----
INSERT INTO roles (role_name) VALUES
  ('admin'),
  ('teamlead'),
  ('labic')
ON CONFLICT (role_name) DO NOTHING;


-- ----- 2. Budget periods (workaround for missing year_no in app code) -----
INSERT INTO budget_periods (period_name, year_no, start_date, end_date, is_closed)
SELECT 'FY2026', 2026, DATE '2026-04-01', DATE '2027-03-31', false
WHERE NOT EXISTS (SELECT 1 FROM budget_periods WHERE period_name = 'FY2026');


-- ----- 3. Spending categories -----
-- "General" is the fallback bucket per team spec.
INSERT INTO spending_categories (category_name, description)
SELECT 'General', 'Fallback when category cannot be auto-classified'
WHERE NOT EXISTS (SELECT 1 FROM spending_categories WHERE category_name = 'General');

INSERT INTO spending_categories (category_name, description)
SELECT 'Consumables', 'Lab consumables and supplies'
WHERE NOT EXISTS (SELECT 1 FROM spending_categories WHERE category_name = 'Consumables');

INSERT INTO spending_categories (category_name, description)
SELECT 'Equipment', 'Lab equipment and instruments'
WHERE NOT EXISTS (SELECT 1 FROM spending_categories WHERE category_name = 'Equipment');

INSERT INTO spending_categories (category_name, description)
SELECT 'Maintenance', 'Lab equipment maintenance and repair'
WHERE NOT EXISTS (SELECT 1 FROM spending_categories WHERE category_name = 'Maintenance');


-- ----- 4. Lab groups -----
-- "General" is the catch-all when WBS doesn't match any group.
-- FCB / ICT match Harry's test_samples/pr_batch_a_realistic.xlsx WBS codes.
INSERT INTO lab_groups (lab_group_name, wbs_code, description)
SELECT 'General', 'GENERAL', 'Fallback group for spending without a confident lab-group match'
WHERE NOT EXISTS (SELECT 1 FROM lab_groups WHERE lab_group_name = 'General');

INSERT INTO lab_groups (lab_group_name, wbs_code, description)
SELECT 'FCB', 'WBS-FCB-001', 'Food, Chemistry and Biology'
WHERE NOT EXISTS (SELECT 1 FROM lab_groups WHERE lab_group_name = 'FCB');

INSERT INTO lab_groups (lab_group_name, wbs_code, description)
SELECT 'ICT', 'WBS-ICT-002', 'Information and Communication Technology'
WHERE NOT EXISTS (SELECT 1 FROM lab_groups WHERE lab_group_name = 'ICT');


-- ----- 5. "General" lab inside EVERY lab group -----
-- This is the per-group fallback lab. Marked is_general so downstream
-- queries (budget engine etc.) can filter unclassified spend cleanly.
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


-- ----- 6. Test users (one per role) -----
-- password_hash is a placeholder. Real auth (W7-02) replaces this later.
-- Team Lead is scoped to FCB so you can test ownership filtering.
INSERT INTO users (role_id, full_name, email, staff_id, password_hash, lab_group_id)
SELECT
  (SELECT role_id FROM roles WHERE role_name = 'admin'),
  'Test Admin',
  'admin@test.local',
  'TEST-ADMIN',
  'placeholder_no_auth_yet',
  NULL
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'admin@test.local');

INSERT INTO users (role_id, full_name, email, staff_id, password_hash, lab_group_id)
SELECT
  (SELECT role_id FROM roles WHERE role_name = 'teamlead'),
  'Test Team Lead (FCB)',
  'teamlead.fcb@test.local',
  'TEST-TL-FCB',
  'placeholder_no_auth_yet',
  (SELECT lab_group_id FROM lab_groups WHERE lab_group_name = 'FCB')
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'teamlead.fcb@test.local');

INSERT INTO users (role_id, full_name, email, staff_id, password_hash, lab_group_id)
SELECT
  (SELECT role_id FROM roles WHERE role_name = 'labic'),
  'Test Lab IC',
  'labic@test.local',
  'TEST-LABIC',
  'placeholder_no_auth_yet',
  NULL
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'labic@test.local');
