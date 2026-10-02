-- ===========================================================
-- Dev seed for Lab Budget Monitoring System
-- Safe to re-run: every insert checks for existence first.
-- Run from project root:
--   PGPASSWORD=postgres psql -U postgres -h localhost -d budget_system \
--     -f backend/seeds/dev_seed.sql
-- ===========================================================


-- ----- 0. Schema tweaks (per Randy + Tim) -----
-- Randy: allow labs.lab_group_id to be NULL. Safe to re-run.
ALTER TABLE labs ALTER COLUMN lab_group_id DROP NOT NULL;

-- Lab IC scoping (W7-02) lives in lab_ic_assignments (many-to-many, optional primary).
-- Fresh DBs get it from db_setup.sql; older DBs: run migrate_lab_ic_to_assignments.sql once.
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Irfan (W9-02 follow-up): source-system PR Status surfaced on PR Records page.
ALTER TABLE purchase_requests ADD COLUMN IF NOT EXISTS pr_status VARCHAR(50);
-- Irfan (W11-03): per-line status (a PR can have lines in different states).
ALTER TABLE purchase_request_lines ADD COLUMN IF NOT EXISTS pr_status VARCHAR(50);

-- Randy (W11-02): For flags on threshold to prevent repeated notifications/emails.
ALTER TABLE labs ADD COLUMN IF NOT EXISTS notified_50 BOOLEAN DEFAULT FALSE;
ALTER TABLE labs ADD COLUMN IF NOT EXISTS notified_80 BOOLEAN DEFAULT FALSE;
ALTER TABLE labs ADD COLUMN IF NOT EXISTS notified_95 BOOLEAN DEFAULT FALSE;
ALTER TABLE labs ADD COLUMN IF NOT EXISTS notified_100 BOOLEAN DEFAULT FALSE;
ALTER TABLE labs ADD COLUMN IF NOT EXISTS alert_period_id BIGINT;
ALTER TABLE labs DROP CONSTRAINT IF EXISTS fk_labs_alert_period;
ALTER TABLE labs ADD CONSTRAINT fk_labs_alert_period FOREIGN KEY (alert_period_id) REFERENCES budget_periods(period_id);

-- Randy (W13-04): Added notifications to lab_groups as well.
ALTER TABLE lab_groups ADD COLUMN IF NOT EXISTS notified_50 boolean DEFAULT false;
ALTER TABLE lab_groups ADD COLUMN IF NOT EXISTS notified_80 boolean DEFAULT false;
ALTER TABLE lab_groups ADD COLUMN IF NOT EXISTS notified_95 boolean DEFAULT false;
ALTER TABLE lab_groups ADD COLUMN IF NOT EXISTS notified_100 boolean DEFAULT false;
ALTER TABLE lab_groups ADD COLUMN IF NOT EXISTS alert_period_id bigint;

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


-- ----- 5b. Specific real labs (handy for cascading-dropdown demos) -----
-- Add new ones here as the team identifies real labs to seed.
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


-- ----- 6. Test users (one per role) -----
-- password_hash is a placeholder. Real auth (W7-02) replaces this later.
-- Team Lead is scoped to FCB so you can test ownership filtering.
INSERT INTO users (role_id, full_name, email, staff_id, password_hash, lab_group_id)
SELECT
  (SELECT role_id FROM roles WHERE role_name = 'admin'),
  'Test Admin',
  'admin@test.com',
  'TEST-ADMIN',
  'placeholder_no_auth_yet',
  NULL
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'admin@test.com');

INSERT INTO users (role_id, full_name, email, staff_id, password_hash, lab_group_id)
SELECT
  (SELECT role_id FROM roles WHERE role_name = 'teamlead'),
  'Test Team Lead (FCB)',
  'teamlead.fcb@test.com',
  'TEST-TL-FCB',
  'placeholder_no_auth_yet',
  (SELECT lab_group_id FROM lab_groups WHERE lab_group_name = 'FCB')
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'teamlead.fcb@test.com');

INSERT INTO users (role_id, full_name, email, staff_id, password_hash, lab_group_id)
SELECT
  (SELECT role_id FROM roles WHERE role_name = 'labic'),
  'Test Lab IC',
  'labic@test.com',
  'TEST-LABIC',
  'placeholder_no_auth_yet',
  NULL
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'labic@test.com');
