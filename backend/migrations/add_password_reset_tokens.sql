-- Run once to add the table. Safe to re-run.
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_id        bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         bigint          NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    temp_password   text            NOT NULL,
    expires_at      timestamptz     NOT NULL,
    used            boolean         NOT NULL DEFAULT false,
    created_at      timestamptz     NOT NULL DEFAULT now()
);

-- If the table already exists but may be missing columns (e.g. older local DBs):
ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS temp_password  text        NOT NULL DEFAULT '';
ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS expires_at     timestamptz NOT NULL DEFAULT now();
ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS used           boolean     NOT NULL DEFAULT false;
ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS created_at     timestamptz NOT NULL DEFAULT now();