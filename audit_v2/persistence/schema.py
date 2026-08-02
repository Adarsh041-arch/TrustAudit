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

# Money fields are TEXT per PHASES_V2 §3.4 (exact Decimal serialization —
# never float). supersedes exists now so Phase 7 deferred re-evaluation
# needs no migration.
CREATE_FINDINGS_SQL = """
CREATE TABLE IF NOT EXISTS findings (
    finding_id           TEXT PRIMARY KEY,
    tenant_id            TEXT NOT NULL,
    document_id          TEXT NOT NULL REFERENCES documents (document_id),
    check_id             TEXT NOT NULL,
    verdict              TEXT NOT NULL,
    severity             TEXT,
    expected_value       TEXT,
    actual_value         TEXT,
    discrepancy          TEXT,
    evidence             JSONB DEFAULT '{}',
    decision_fingerprint TEXT NOT NULL,
    supersedes           TEXT REFERENCES findings (finding_id),
    engine_version       TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, document_id, check_id, decision_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_findings_tenant_doc ON findings (tenant_id, document_id);
"""

# RLS: every tenant-scoped table gets FORCE ROW LEVEL SECURITY and a policy
# keyed to the app.tenant_id GUC set per-transaction by tenant_session().
_RLS_TABLES = ("documents", "reconciliation_log", "findings")

ENABLE_RLS_SQL = "\n".join(
    f"""
ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {t} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_{t} ON {t};
CREATE POLICY tenant_isolation_{t} ON {t}
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
"""
    for t in _RLS_TABLES
)

# Non-superuser app role for RLS — superusers bypass row-level security.
# The application connects as this user so RLS policies actually enforce
# tenant isolation.
SETUP_APP_ROLE_SQL = """
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user WITH LOGIN PASSWORD 'app_dev_password';
    END IF;
END $$;
GRANT CONNECT ON DATABASE audit_v2 TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
"""

ALL_SCHEMA_SQL = (
    SETUP_APP_ROLE_SQL + CREATE_SCHEMA_SQL + CREATE_RECONCILIATION_SQL
    + CREATE_FINDINGS_SQL + ENABLE_RLS_SQL
)
