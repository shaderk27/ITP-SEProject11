-- =============================================================================
-- STEP 2 OF 2 — Run this second, connected to the 'budget_system' database
--               (switch to it in pgAdmin's connection dropdown, then run this)
--
-- Sections: 1. Access Control  2. Lab Hierarchy & Mapping
--           3. Categories & Budgeting  4. Upload & Staging
--           5. Review Workflow  6. Finalized Transaction Storage
--           7. Duplicate Handling & Version History
--           8. Alerts & Auditability  9. Chatbot Queries
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Drop all tables if they exist (reverse dependency order to avoid FK errors)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS chatbot_queries               CASCADE;
DROP TABLE IF EXISTS audit_logs                    CASCADE;
DROP TABLE IF EXISTS budget_alerts                 CASCADE;
DROP TABLE IF EXISTS alert_thresholds              CASCADE;
DROP TABLE IF EXISTS pr_versions                   CASCADE;
DROP TABLE IF EXISTS duplicate_detection_results   CASCADE;
DROP TABLE IF EXISTS purchase_request_lines        CASCADE;
DROP TABLE IF EXISTS purchase_requests             CASCADE;
DROP TABLE IF EXISTS review_actions                CASCADE;
DROP TABLE IF EXISTS review_queue_items            CASCADE;
DROP TABLE IF EXISTS staging_pr_lines              CASCADE;
DROP TABLE IF EXISTS staging_pr_headers            CASCADE;
DROP TABLE IF EXISTS upload_batches                CASCADE;
DROP TABLE IF EXISTS budgets                       CASCADE;
DROP TABLE IF EXISTS budget_periods                CASCADE;
DROP TABLE IF EXISTS spending_categories           CASCADE;
DROP TABLE IF EXISTS requester_lab_mappings        CASCADE;
DROP TABLE IF EXISTS lab_aliases                   CASCADE;
DROP TABLE IF EXISTS labs                          CASCADE;
DROP TABLE IF EXISTS users                         CASCADE;
DROP TABLE IF EXISTS lab_groups                    CASCADE;
DROP TABLE IF EXISTS roles                         CASCADE;

-- -----------------------------------------------------------------------------
-- Utility: auto-update updated_at columns
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;


-- =============================================================================
-- 1. ACCESS CONTROL
-- =============================================================================

CREATE TABLE roles (
    role_id     bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role_name   varchar(50)     NOT NULL UNIQUE,
    created_at  timestamptz     NOT NULL DEFAULT now()
);

-- NOTE: users references lab_groups, which is defined in section 2.
-- lab_group_id FK is added via ALTER TABLE after lab_groups is created.
CREATE TABLE users (
    user_id         bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role_id         bigint          NOT NULL,
    full_name       varchar(150)    NOT NULL,
    email           varchar(255)    NOT NULL UNIQUE,
    staff_id        varchar(50)     UNIQUE,
    password_hash   text            NOT NULL,
    created_at      timestamptz     NOT NULL DEFAULT now(),
    updated_at      timestamptz     NOT NULL DEFAULT now(),
    lab_group_id    bigint          -- FK added after lab_groups is created
);

CREATE TRIGGER set_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- =============================================================================
-- 2. LAB HIERARCHY & MAPPING
-- =============================================================================

CREATE TABLE lab_groups (
    lab_group_id    bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lab_group_name  varchar(120)    NOT NULL,
    wbs_code        varchar(100)    NOT NULL UNIQUE,
    description     text,
    created_at      timestamptz     NOT NULL DEFAULT now()
);

-- Now that lab_groups exists, add the FK on users
ALTER TABLE users
    ADD CONSTRAINT fk_users_role
        FOREIGN KEY (role_id)       REFERENCES roles (role_id),
    ADD CONSTRAINT fk_users_lab_group
        FOREIGN KEY (lab_group_id)  REFERENCES lab_groups (lab_group_id);

CREATE TABLE labs (
    lab_id          bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lab_group_id    bigint          NOT NULL REFERENCES lab_groups (lab_group_id),
    lab_code        varchar(50)     NOT NULL UNIQUE,
    lab_name        varchar(150)    NOT NULL,
    venue           text,
    is_general      boolean         NOT NULL DEFAULT false,
    created_at      timestamptz     NOT NULL DEFAULT now()
);

CREATE TABLE lab_aliases (
    lab_alias_id    bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lab_id          bigint          NOT NULL REFERENCES labs (lab_id) ON DELETE CASCADE,
    alias_text      varchar(200)    NOT NULL,
    alias_type      varchar(50)     NOT NULL,
    UNIQUE (lab_id, alias_text)
);

CREATE TABLE requester_lab_mappings (
    requester_mapping_id    bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    requester_name          varchar(150),
    requester_email         varchar(255),
    default_lab_id          bigint          NOT NULL REFERENCES labs (lab_id),
    confidence_note         text,
    is_active               boolean         NOT NULL DEFAULT true,
    created_at              timestamptz     NOT NULL DEFAULT now()
);


-- =============================================================================
-- 3. CATEGORIES & BUDGETING
-- =============================================================================

CREATE TABLE spending_categories (
    category_id     bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_name   varchar(100)    NOT NULL UNIQUE,
    description     text,
    created_at      timestamptz     NOT NULL DEFAULT now()
);

CREATE TABLE budget_periods (
    period_id       bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_name     varchar(100)    NOT NULL,
    year_no         integer         NOT NULL,
    start_date      date            NOT NULL,
    end_date        date            NOT NULL,
    is_closed       boolean         NOT NULL DEFAULT false,
    UNIQUE (year_no, start_date, end_date)
);

CREATE TABLE budgets (
    budget_id       bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_id       bigint          NOT NULL REFERENCES budget_periods (period_id),
    lab_group_id    bigint          REFERENCES lab_groups (lab_group_id),
    lab_id          bigint          REFERENCES labs (lab_id),
    category_id     bigint          REFERENCES spending_categories (category_id),
    budget_amount   numeric(14,2)   NOT NULL CHECK (budget_amount >= 0),
    created_by      bigint          REFERENCES users (user_id),
    created_at      timestamptz     NOT NULL DEFAULT now(),
    updated_at      timestamptz     NOT NULL DEFAULT now(),
    -- At least one of lab_group_id, lab_id, category_id must be non-null
    CONSTRAINT chk_budgets_scope
        CHECK (
            lab_group_id IS NOT NULL
            OR lab_id    IS NOT NULL
            OR category_id IS NOT NULL
        )
);

CREATE TRIGGER set_budgets_updated_at
BEFORE UPDATE ON budgets
FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- =============================================================================
-- 4. UPLOAD & STAGING
-- =============================================================================

CREATE TABLE upload_batches (
    batch_id            bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uploaded_by         bigint          NOT NULL REFERENCES users (user_id),
    filename            varchar(255)    NOT NULL,
    file_type           varchar(20)     NOT NULL,
    upload_status       varchar(30)     NOT NULL,
    validation_message  text,
    uploaded_at         timestamptz     NOT NULL DEFAULT now(),
    processed_at        timestamptz
);

CREATE TABLE staging_pr_headers (
    staging_header_id       bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id                bigint          NOT NULL REFERENCES upload_batches (batch_id) ON DELETE CASCADE,
    source_pr_number        varchar(50)     NOT NULL,
    req_type                varchar(150),
    pr_sub_date             date,
    requestor_name          varchar(150),
    purpose                 text,
    grand_total_sgd         numeric(14,2),
    wbs_code                varchar(100),
    instruction_to_vendor   text,
    raw_header_json         jsonb,
    created_at              timestamptz     NOT NULL DEFAULT now(),
    UNIQUE (batch_id, source_pr_number)
);

CREATE TABLE staging_pr_lines (
    staging_line_id         bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    staging_header_id       bigint          NOT NULL REFERENCES staging_pr_headers (staging_header_id) ON DELETE CASCADE,
    source_line_no          integer,
    item_details            text,
    qty                     numeric(14,2),
    unit_rate               numeric(14,2),
    raw_pr_category         varchar(100),
    raw_lab_text            varchar(150),
    amount_gst              numeric(14,2),
    suggested_lab_group_id  bigint          REFERENCES lab_groups (lab_group_id),
    suggested_lab_id        bigint          REFERENCES labs (lab_id),
    suggested_category_id   bigint          REFERENCES spending_categories (category_id),
    classification_status   varchar(30)     NOT NULL DEFAULT 'pending',
    duplicate_status        varchar(30)     NOT NULL DEFAULT 'unchecked',
    review_status           varchar(30)     NOT NULL DEFAULT 'not_required',
    match_confidence        numeric(5,2),
    match_reason            text,
    raw_line_json           jsonb,
    created_at              timestamptz     NOT NULL DEFAULT now()
);


-- =============================================================================
-- 5. REVIEW WORKFLOW
-- =============================================================================

CREATE TABLE review_queue_items (
    review_queue_id     bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    staging_line_id     bigint          NOT NULL REFERENCES staging_pr_lines (staging_line_id) ON DELETE CASCADE,
    assigned_to_user_id bigint          REFERENCES users (user_id),
    queue_status        varchar(30)     NOT NULL DEFAULT 'open',
    priority            varchar(20)     NOT NULL DEFAULT 'normal',
    review_reason       text,
    created_at          timestamptz     NOT NULL DEFAULT now(),
    resolved_at         timestamptz
);

CREATE TABLE review_actions (
    review_action_id    bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    review_queue_id     bigint          NOT NULL REFERENCES review_queue_items (review_queue_id) ON DELETE CASCADE,
    reviewed_by         bigint          NOT NULL REFERENCES users (user_id),
    final_lab_group_id  bigint          REFERENCES lab_groups (lab_group_id),
    final_lab_id        bigint          REFERENCES labs (lab_id),
    final_category_id   bigint          REFERENCES spending_categories (category_id),
    action_type         varchar(30)     NOT NULL,
    review_comment      text,
    reviewed_at         timestamptz     NOT NULL DEFAULT now()
);


-- =============================================================================
-- 6. FINALIZED TRANSACTION STORAGE
-- =============================================================================

CREATE TABLE purchase_requests (
    pr_id                   bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_pr_number        varchar(50)     NOT NULL,
    latest_batch_id         bigint          REFERENCES upload_batches (batch_id),
    requestor_name          varchar(150),
    req_type                varchar(150),
    request_date            date,
    purpose                 text,
    wbs_code                varchar(100),
    instruction_to_vendor   text,
    grand_total_sgd         numeric(14,2),
    lab_group_id            bigint          REFERENCES lab_groups (lab_group_id),
    created_at              timestamptz     NOT NULL DEFAULT now(),
    updated_at              timestamptz     NOT NULL DEFAULT now()
);

CREATE TRIGGER set_purchase_requests_updated_at
BEFORE UPDATE ON purchase_requests
FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TABLE purchase_request_lines (
    pr_line_id              bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pr_id                   bigint          NOT NULL REFERENCES purchase_requests (pr_id) ON DELETE CASCADE,
    line_no                 integer,
    item_description        text,
    qty                     numeric(14,2),
    unit_rate               numeric(14,2),
    amount_gst              numeric(14,2)   NOT NULL,
    currency_code           varchar(10)     NOT NULL DEFAULT 'SGD',
    lab_id                  bigint          REFERENCES labs (lab_id),
    category_id             bigint          REFERENCES spending_categories (category_id),
    source_staging_line_id  bigint          REFERENCES staging_pr_lines (staging_line_id),
    created_at              timestamptz     NOT NULL DEFAULT now()
);


-- =============================================================================
-- 7. DUPLICATE HANDLING & VERSION HISTORY
-- =============================================================================

CREATE TABLE duplicate_detection_results (
    duplicate_result_id bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    staging_line_id     bigint          NOT NULL REFERENCES staging_pr_lines (staging_line_id) ON DELETE CASCADE,
    matched_pr_line_id  bigint          REFERENCES purchase_request_lines (pr_line_id),
    duplicate_type      varchar(30)     NOT NULL,
    confidence_score    numeric(5,2),
    detection_reason    text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE TABLE pr_versions (
    version_id      bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pr_id           bigint          NOT NULL REFERENCES purchase_requests (pr_id) ON DELETE CASCADE,
    batch_id        bigint          REFERENCES upload_batches (batch_id),
    change_type     varchar(30)     NOT NULL,
    old_data        jsonb,
    new_data        jsonb,
    changed_by      bigint          REFERENCES users (user_id),
    change_reason   text,
    changed_at      timestamptz     NOT NULL DEFAULT now()
);


-- =============================================================================
-- 8. ALERTS & AUDITABILITY
-- =============================================================================

CREATE TABLE alert_thresholds (
    threshold_id        bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    threshold_percent   numeric(5,2)    NOT NULL CHECK (threshold_percent > 0),
    scope_type          varchar(30)     NOT NULL,
    UNIQUE (threshold_percent, scope_type)
);

CREATE TABLE budget_alerts (
    alert_id            bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    budget_id           bigint          NOT NULL REFERENCES budgets (budget_id) ON DELETE CASCADE,
    threshold_id        bigint          NOT NULL REFERENCES alert_thresholds (threshold_id),
    current_spend       numeric(14,2)   NOT NULL,
    budget_amount       numeric(14,2)   NOT NULL,
    alert_status        varchar(30)     NOT NULL DEFAULT 'open',
    sent_to_user_id     bigint          REFERENCES users (user_id),
    triggered_at        timestamptz     NOT NULL DEFAULT now(),
    resolved_at         timestamptz
);

CREATE TABLE audit_logs (
    audit_id        bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         bigint          REFERENCES users (user_id),
    action_type     varchar(50)     NOT NULL,
    entity_name     varchar(100)    NOT NULL,
    record_id       varchar(100)    NOT NULL,
    old_value       jsonb,
    new_value       jsonb,
    ip_address      inet,
    created_at      timestamptz     NOT NULL DEFAULT now()
);


-- =============================================================================
-- 9. CHATBOT QUERIES (ITP2)
-- =============================================================================

CREATE TABLE chatbot_queries (
    query_id            bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id             bigint          NOT NULL REFERENCES users (user_id),
    question_text       text            NOT NULL,
    generated_sql       text,
    response_summary    text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);


-- =============================================================================
-- INDEXES
-- (covers all FK columns and common query filters not already covered by UNIQUE)
-- =============================================================================

-- users
CREATE INDEX idx_users_role_id        ON users (role_id);
CREATE INDEX idx_users_lab_group_id   ON users (lab_group_id);

-- labs
CREATE INDEX idx_labs_lab_group_id    ON labs (lab_group_id);

-- lab_aliases
CREATE INDEX idx_lab_aliases_lab_id   ON lab_aliases (lab_id);

-- requester_lab_mappings
CREATE INDEX idx_req_lab_map_lab_id   ON requester_lab_mappings (default_lab_id);

-- budgets
CREATE INDEX idx_budgets_period_id    ON budgets (period_id);
CREATE INDEX idx_budgets_lab_group_id ON budgets (lab_group_id);
CREATE INDEX idx_budgets_lab_id       ON budgets (lab_id);
CREATE INDEX idx_budgets_category_id  ON budgets (category_id);

-- upload_batches
CREATE INDEX idx_upload_batches_user  ON upload_batches (uploaded_by);

-- staging_pr_headers
CREATE INDEX idx_sph_batch_id         ON staging_pr_headers (batch_id);

-- staging_pr_lines
CREATE INDEX idx_spl_header_id        ON staging_pr_lines (staging_header_id);
CREATE INDEX idx_spl_classification   ON staging_pr_lines (classification_status);
CREATE INDEX idx_spl_review_status    ON staging_pr_lines (review_status);

-- review_queue_items
CREATE INDEX idx_rqi_staging_line_id  ON review_queue_items (staging_line_id);
CREATE INDEX idx_rqi_assigned_user    ON review_queue_items (assigned_to_user_id);
CREATE INDEX idx_rqi_queue_status     ON review_queue_items (queue_status);

-- review_actions
CREATE INDEX idx_ra_queue_id          ON review_actions (review_queue_id);
CREATE INDEX idx_ra_reviewed_by       ON review_actions (reviewed_by);

-- purchase_requests
CREATE INDEX idx_pr_source_number     ON purchase_requests (source_pr_number);
CREATE INDEX idx_pr_lab_group_id      ON purchase_requests (lab_group_id);

-- purchase_request_lines
CREATE INDEX idx_prl_pr_id            ON purchase_request_lines (pr_id);
CREATE INDEX idx_prl_lab_id           ON purchase_request_lines (lab_id);
CREATE INDEX idx_prl_category_id      ON purchase_request_lines (category_id);

-- duplicate_detection_results
CREATE INDEX idx_ddr_staging_line_id  ON duplicate_detection_results (staging_line_id);

-- pr_versions
CREATE INDEX idx_prv_pr_id            ON pr_versions (pr_id);

-- budget_alerts
CREATE INDEX idx_ba_budget_id         ON budget_alerts (budget_id);
CREATE INDEX idx_ba_alert_status      ON budget_alerts (alert_status);

-- audit_logs
CREATE INDEX idx_al_user_id           ON audit_logs (user_id);
CREATE INDEX idx_al_entity_name       ON audit_logs (entity_name);
CREATE INDEX idx_al_created_at        ON audit_logs (created_at);

-- chatbot_queries
CREATE INDEX idx_cq_user_id           ON chatbot_queries (user_id);
