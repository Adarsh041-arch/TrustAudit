CREATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    document_id        TEXT PRIMARY KEY,
    tenant_id          TEXT NOT NULL,
    source_uri         TEXT,
    content_hash       TEXT NOT NULL,
    doc_type           TEXT,
    doc_type_confidence REAL,
    batch_id           TEXT,
    ingestion_run_id   TEXT,
    status             TEXT NOT NULL DEFAULT 'RECEIVED',
    extractor_version  TEXT,
    page_count         INTEGER,
    pages_examined     INTEGER,
    pages_unreadable   INTEGER[] DEFAULT '{}',
    coverage_complete  BOOLEAN DEFAULT FALSE,
    pii_classes        TEXT[] DEFAULT '{}',
    residency_region   TEXT,
    schema_version     TEXT DEFAULT '2.0',
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_documents_tenant_status ON documents (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_documents_tenant_hash ON documents (tenant_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_batch ON documents (batch_id);
"""

CREATE_RECONCILIATION_SQL = """
CREATE TABLE IF NOT EXISTS reconciliation_log (
    run_id            TEXT PRIMARY KEY,
    tenant_id         TEXT NOT NULL,
    accepted          INTEGER NOT NULL,
    completed         INTEGER NOT NULL,
    quarantined       INTEGER NOT NULL,
    failed            INTEGER NOT NULL,
    in_flight         INTEGER NOT NULL,
    discrepancy       INTEGER NOT NULL,
    checked_at        TIMESTAMPTZ DEFAULT NOW()
);
"""
