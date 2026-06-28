-- W7-02/03 minimal auth seed.
-- Uses only the current W7-compatible auth/config tables.

ALTER TABLE users
ADD COLUMN IF NOT EXISTS lab_id BIGINT REFERENCES labs(lab_id);

INSERT INTO roles (role_id, role_name)
OVERRIDING SYSTEM VALUE
VALUES
    (1, 'admin'),
    (2, 'teamlead'),
    (3, 'labic')
ON CONFLICT (role_id) DO UPDATE
SET role_name = EXCLUDED.role_name;

INSERT INTO lab_groups (lab_group_id, lab_group_name, wbs_code, description)
OVERRIDING SYSTEM VALUE
VALUES
    (1, 'Food, Chemical and Biotechnology', 'FCB', 'Development lab group for local auth and access checks'),
    (2, 'Infocomm Technology', 'ICT', 'Development lab group for local auth and access checks')
ON CONFLICT (lab_group_id) DO UPDATE
SET
    lab_group_name = EXCLUDED.lab_group_name,
    wbs_code = EXCLUDED.wbs_code,
    description = EXCLUDED.description;

INSERT INTO labs (lab_id, lab_group_id, lab_code, lab_name, venue, is_general)
OVERRIDING SYSTEM VALUE
VALUES
    (1, 1, 'FCB-LAB-1', 'FCB Teaching Lab 1', 'SIT FCB Block', FALSE),
    (2, 1, 'FCB-LAB-2', 'FCB Research Lab 2', 'SIT FCB Block', FALSE),
    (3, 2, 'ICT-LAB-1', 'ICT Project Lab 1', 'SIT ICT Block', FALSE)
ON CONFLICT (lab_id) DO UPDATE
SET
    lab_group_id = EXCLUDED.lab_group_id,
    lab_code = EXCLUDED.lab_code,
    lab_name = EXCLUDED.lab_name,
    venue = EXCLUDED.venue,
    is_general = EXCLUDED.is_general;

INSERT INTO users (
    user_id,
    role_id,
    full_name,
    email,
    staff_id,
    password_hash,
    lab_group_id,
    lab_id
)
OVERRIDING SYSTEM VALUE
VALUES
    (1, 1, 'Development Admin', 'admin@example.com', 'DEV-ADMIN', 'placeholder_no_auth_yet', NULL, NULL),
    (2, 2, 'Development Team Lead', 'teamlead.fcb@example.com', 'DEV-TL-FCB', 'placeholder_no_auth_yet', 1, NULL),
    (3, 3, 'Development Lab IC', 'labic.fcb@example.com', 'DEV-LIC-FCB', 'placeholder_no_auth_yet', NULL, 1),
    (4, 3, 'ICT Lab IC', 'labic.ict@example.com', 'DEV-LIC-ICT', 'placeholder_no_auth_yet', NULL, 3),
    (5, 3, 'NONE Lab IC', 'labic.non@example.com', 'DEV-LIC-NON', 'placeholder_no_auth_yet', NULL, NULL),
	(6, 2, 'NONE Team Lead', 'teamlead.non@example.com', 'DEV-TL-NON', 'placeholder_no_auth_yet', NULL, NULL)
ON CONFLICT (user_id) DO UPDATE
SET
    role_id = EXCLUDED.role_id,
    full_name = EXCLUDED.full_name,
    email = EXCLUDED.email,
    staff_id = EXCLUDED.staff_id,
    password_hash = EXCLUDED.password_hash,
    lab_group_id = EXCLUDED.lab_group_id,
    lab_id = EXCLUDED.lab_id;

SELECT setval(pg_get_serial_sequence('roles', 'role_id'), (SELECT MAX(role_id) FROM roles));
SELECT setval(pg_get_serial_sequence('lab_groups', 'lab_group_id'), (SELECT MAX(lab_group_id) FROM lab_groups));
SELECT setval(pg_get_serial_sequence('labs', 'lab_id'), (SELECT MAX(lab_id) FROM labs));
SELECT setval(pg_get_serial_sequence('users', 'user_id'), (SELECT MAX(user_id) FROM users));
