"""DocumentStore contract tests (Memory + Postgres) and RLS tenant isolation.

Postgres tests skip unless AUDIT_PG_DSN is set (CI/docker-compose provides it).
The RLS test enumerates tenant-scoped tables from information_schema so a new
table added without RLS fails the build.
"""
from __future__ import annotations

import os
import uuid

import pytest

from audit_v2.ingestion.document_store import MemoryDocumentStore

DSN = os.getenv("AUDIT_PG_DSN")
# App user must be non-superuser so RLS policies actually enforce isolation.
APP_DSN = os.getenv("AUDIT_PG_APP_DSN", "postgresql://app_user:app_dev_password@127.0.0.1:5432/audit_v2")

requires_pg = pytest.mark.skipif(not DSN, reason="AUDIT_PG_DSN not set")


@pytest.fixture(scope="session")
def _admin_conn():
    """Superuser connection — used only to apply schema (DDL needs superuser)."""
    if not DSN:
        pytest.skip("AUDIT_PG_DSN not set")
    from audit_v2.persistence.db import connect

    conn = connect(DSN)
    from audit_v2.persistence.db import apply_schema

    apply_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def pg_conn(_admin_conn):
    """Non-superuser connection — RLS actually enforces here."""
    from audit_v2.persistence.db import connect

    conn = connect(APP_DSN)
    yield conn
    conn.close()


def _pg_store(conn, tenant_id):
    from audit_v2.ingestion.document_store import PostgresDocumentStore

    return PostgresDocumentStore(conn, tenant_id)


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    if request.param == "memory":
        yield MemoryDocumentStore()
    else:
        if not DSN:
            pytest.skip("AUDIT_PG_DSN not set")
        request.getfixturevalue("_admin_conn")  # apply schema first
        from audit_v2.persistence.db import connect

        conn = connect(APP_DSN)
        yield _pg_store(conn, f"t-{uuid.uuid4().hex[:8]}")
        conn.close()


class TestDocumentStoreContract:
    def test_create_and_get(self, store):
        tenant = getattr(store, "_tenant_id", "tenant-a")
        rec = store.create(tenant, "hash-1", doc_type="invoice", batch_id="b1")
        assert rec.status == "RECEIVED"
        assert store.get(rec.document_id).content_hash == "hash-1"

    def test_update_status(self, store):
        tenant = getattr(store, "_tenant_id", "tenant-a")
        rec = store.create(tenant, "hash-2")
        store.update_status(rec.document_id, "READY")
        assert store.get(rec.document_id).status == "READY"

    def test_dedup_by_hash(self, store):
        tenant = getattr(store, "_tenant_id", "tenant-a")
        first = store.create(tenant, "hash-3")
        dup = store.create(tenant, "hash-3")
        assert dup.duplicate_of == first.document_id

    def test_count_by_status(self, store):
        tenant = getattr(store, "_tenant_id", "tenant-a")
        store.create(tenant, "hash-4")
        store.create(tenant, "hash-5")
        counts = store.count_by_status(tenant)
        assert counts.get("RECEIVED", 0) >= 2

    def test_get_missing_returns_none(self, store):
        assert store.get("doc_does_not_exist") is None


@requires_pg
class TestRLSIsolation:
    def test_cross_tenant_invisible(self, pg_conn):
        ta, tb = f"ta-{uuid.uuid4().hex[:8]}", f"tb-{uuid.uuid4().hex[:8]}"
        _pg_store(pg_conn, ta).create(ta, "secret-hash-a")
        store_b = _pg_store(pg_conn, tb)
        assert store_b.get_by_hash(ta, "secret-hash-a") is None
        assert store_b.count_by_status(ta) == {}

    def test_every_tenant_table_has_rls(self, pg_conn):
        """Any table with a tenant_id column must have RLS enabled+forced."""
        rows = pg_conn.execute(
            """
            SELECT c.table_name, t.relrowsecurity, t.relforcerowsecurity
            FROM information_schema.columns c
            JOIN pg_class t ON t.relname = c.table_name
            JOIN pg_namespace n ON n.oid = t.relnamespace AND n.nspname = 'public'
            WHERE c.column_name = 'tenant_id' AND c.table_schema = 'public'
              AND t.relkind = 'r'
            """
        ).fetchall()
        assert rows, "no tenant-scoped tables found — schema not applied?"
        missing = [r[0] for r in rows if not (r[1] and r[2])]
        assert not missing, f"tables without forced RLS: {missing}"

    def test_findings_rls(self, pg_conn):
        from audit_v2.persistence.finding_store import FindingStore

        ta, tb = f"ta-{uuid.uuid4().hex[:8]}", f"tb-{uuid.uuid4().hex[:8]}"
        doc = _pg_store(pg_conn, ta).create(ta, f"h-{uuid.uuid4().hex[:8]}")
        FindingStore(pg_conn, ta).insert({
            "finding_id": f"f-{uuid.uuid4().hex[:8]}",
            "document_id": doc.document_id,
            "check_id": "CHK-TEST-001",
            "verdict": "FAIL",
            "severity": "high",
            "decision_fingerprint": "fp-1",
        })
        assert FindingStore(pg_conn, ta).list_by_document(doc.document_id)
        assert FindingStore(pg_conn, tb).list_by_document(doc.document_id) == []
