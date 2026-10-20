-- =============================================================================
-- W13-03A RAG storage: knowledge_documents + knowledge_chunks (pgvector).
-- Non-destructive: only creates what is missing. Safe to re-run. Inserts no
-- data. Run on existing DBs, and again after a fresh db_setup.sql reset
-- (db_setup.sql does not create these tables, so fresh setups that never use
-- RAG don't need pgvector installed).
--
--   PGPASSWORD=postgres psql -U postgres -h localhost -d budget_system \
--     -f backend/migrations/add_rag_knowledge.sql
--
-- Needs the pgvector extension available on the server:
--   macOS (Homebrew):  brew install pgvector
--   Ubuntu/Debian:     apt install postgresql-<major>-pgvector
-- CREATE EXTENSION needs a role allowed to create extensions (superuser, or
-- pg_database_owner on PG13+ for trusted extensions). Check this on Lightsail
-- before running there.
--
-- Design notes:
--   * One chunks table for both sources. source_type says which, and exactly
--     one of document_id / pr_line_id is set.
--   * Role scope is NOT copied onto chunks. PR-line chunks are scoped at query
--     time by joining purchase_request_lines -> labs -> lab_groups, so a lab
--     correction, a lab moving group, or a Lab IC reassignment applies to
--     retrieval immediately with no re-index. Documents use visible_roles.
--   * embedding has no fixed dimension, so switching embedding model doesn't
--     need a schema change. Every search filters on embedding_model, because
--     vectors from different models can't be compared. Exact (unindexed)
--     search is fast enough at this project's size (thousands of rows); add a
--     per-model HNSW index later only if search becomes slow.
--   * Deleting a document or PR line cascades to its chunks. is_active lets
--     a chunk be retired without deleting it (e.g. a superseded doc version).
-- =============================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- Approved client documents (policies, SOPs, procurement guidelines, guides).
CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id         bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title               varchar(255)    NOT NULL,
    source_filename     varchar(255)    NOT NULL,
    document_version    varchar(50)     NOT NULL,
    -- Roles allowed to retrieve this document. Visibility must be approved
    -- explicitly per document, so the default is nobody.
    visible_roles       text[]          NOT NULL DEFAULT '{}',
    is_active           boolean         NOT NULL DEFAULT true,
    uploaded_by         bigint          REFERENCES users (user_id) ON DELETE SET NULL,
    created_at          timestamptz     NOT NULL DEFAULT now(),
    updated_at          timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT uq_kd_file_version UNIQUE (source_filename, document_version),
    CONSTRAINT ck_kd_visible_roles
        CHECK (visible_roles <@ ARRAY['admin', 'teamlead', 'labic']::text[])
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id            bigint          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_type         varchar(20)     NOT NULL,
    document_id         bigint          REFERENCES knowledge_documents (document_id) ON DELETE CASCADE,
    pr_line_id          bigint          REFERENCES purchase_request_lines (pr_line_id) ON DELETE CASCADE,
    chunk_index         integer         NOT NULL DEFAULT 0,
    -- Human-readable citation shown with answers, e.g. "PR 4500012345 line 2".
    source_ref          varchar(255)    NOT NULL,
    content             text            NOT NULL,
    -- sha256 hex of content: unchanged text is not re-embedded.
    content_hash        char(64)        NOT NULL,
    embedding           vector          NOT NULL,
    -- Provider + model that produced the embedding, e.g. "local:BAAI/bge-small-en-v1.5".
    embedding_model     varchar(150)    NOT NULL,
    is_active           boolean         NOT NULL DEFAULT true,
    created_at          timestamptz     NOT NULL DEFAULT now(),
    updated_at          timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT ck_kc_source CHECK (
        (source_type = 'document' AND document_id IS NOT NULL AND pr_line_id IS NULL)
        OR (source_type = 'pr_line' AND pr_line_id IS NOT NULL AND document_id IS NULL)
    )
);

-- One chunk per (source, position, model): re-indexing upserts, never duplicates.
CREATE UNIQUE INDEX IF NOT EXISTS uq_kc_document_chunk
    ON knowledge_chunks (document_id, chunk_index, embedding_model)
    WHERE document_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_kc_pr_line_chunk
    ON knowledge_chunks (pr_line_id, chunk_index, embedding_model)
    WHERE pr_line_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_kc_model_active
    ON knowledge_chunks (embedding_model, source_type)
    WHERE is_active;

-- updated_at triggers (trigger_set_updated_at comes from db_setup.sql).
DROP TRIGGER IF EXISTS set_updated_at_knowledge_documents ON knowledge_documents;
CREATE TRIGGER set_updated_at_knowledge_documents
BEFORE UPDATE ON knowledge_documents
FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

DROP TRIGGER IF EXISTS set_updated_at_knowledge_chunks ON knowledge_chunks;
CREATE TRIGGER set_updated_at_knowledge_chunks
BEFORE UPDATE ON knowledge_chunks
FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
INSERT INTO schema_migrations (migration_name)
VALUES ('add_rag_knowledge')
ON CONFLICT (migration_name) DO NOTHING;
COMMIT;
