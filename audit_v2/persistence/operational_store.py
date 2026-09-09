"""Transactional tenant state, immutable versions, and committed events.

SQLite is the single-process local adapter. Postgres uses tenant RLS and an
advisory transaction lock so multiple API workers cannot overwrite a tenant.
The transaction stays open only during deterministic commit, never model IO.
"""

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


class StateTransaction:
    def __init__(self, connection, tenant_id: str, postgres: bool):
        self.connection = connection
        self.tenant_id = tenant_id
        self.postgres = postgres

    def execute(self, sql, args=()):
        return self.connection.execute(sql.replace("?", "%s") if self.postgres else sql, args)

    def load(self) -> dict | None:
        row = self.execute(
            "SELECT payload, fingerprint FROM audit_operational_state WHERE tenant_id=?",
            (self.tenant_id,),
        ).fetchone()
        if row is None:
            return None
        if hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
            raise ValueError("Stored audit state failed its integrity check")
        return json.loads(row[0])

    def save(self, value: dict, event: str = "audit_state_committed") -> str:
        # Independent product modules share tenant state without erasing each other.
        existing = self.load() or {}
        for section in ("reconciliation_runs", "operations", "corrections", "jobs", "cancelled_operations"):
            if section in existing and section not in value:
                value = {**value, section: existing[section]}
        payload = json.dumps(value, sort_keys=True, default=str)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        row = self.execute(
            "SELECT fingerprint FROM audit_operational_state WHERE tenant_id=?", (self.tenant_id,)
        ).fetchone()
        if row and row[0] == digest:
            return digest
        now = datetime.now(UTC).isoformat()
        revision_id = uuid.uuid4().hex
        self.execute(
            "INSERT INTO audit_state_history (revision_id, tenant_id, payload, "
            "fingerprint, created_at) VALUES (?, ?, ?, ?, ?)",
            (revision_id, self.tenant_id, payload, digest, now),
        )
        self.execute(
            "INSERT INTO audit_operational_state (tenant_id, payload, "
            "fingerprint) VALUES (?, ?, ?) "
            "ON CONFLICT (tenant_id) DO UPDATE SET payload=excluded.payload, "
            "fingerprint=excluded.fingerprint",
            (self.tenant_id, payload, digest),
        )
        self.execute(
            "INSERT INTO audit_outbox (event_id, tenant_id, event_type, "
            "revision_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, self.tenant_id, event, revision_id, now),
        )
        return digest


class OperationalStore:
    def __init__(self, path: str | Path | None = None, dsn: str | None = None):
        self.dsn = dsn
        self.path = Path(path or os.getenv("V2_OPERATIONAL_DB") or ".data/operational.sqlite3")
        if not dsn:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            if dsn:
                role = db.execute(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
                ).fetchone()
                if role is None or role[0] or role[1]:
                    raise RuntimeError("Audit database role must not bypass row-level security")
            statements = [
                "CREATE TABLE IF NOT EXISTS audit_operational_state (tenant_id TEXT "
                "PRIMARY KEY, payload TEXT NOT NULL, fingerprint TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS audit_state_history (revision_id TEXT "
                "PRIMARY KEY, tenant_id TEXT NOT NULL, payload TEXT NOT NULL, "
                "fingerprint TEXT NOT NULL, created_at TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS audit_outbox (event_id TEXT PRIMARY KEY, "
                "tenant_id TEXT NOT NULL, event_type TEXT NOT NULL, revision_id TEXT "
                "NOT NULL, created_at TEXT NOT NULL)",
            ]
            for sql in statements:
                db.execute(sql)
            if dsn:
                for table in ("audit_operational_state", "audit_state_history", "audit_outbox"):
                    db.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
                    db.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
                    # Deployment migrations own policy creation; creation is idempotent here.
                    exists = db.execute(
                        "SELECT 1 FROM pg_policies WHERE tablename=%s AND policyname=%s",
                        (table, "tenant_isolation"),
                    ).fetchone()
                    if not exists:
                        db.execute(
                            f"CREATE POLICY tenant_isolation ON {table} USING (tenant_id = "
                            f"current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = "
                            f"current_setting('app.tenant_id', true))"
                        )

    @contextmanager
    def _connect(self):
        if self.dsn:
            import psycopg

            with psycopg.connect(self.dsn) as db:
                yield db
        else:
            db = sqlite3.connect(self.path, timeout=30)
            try:
                db.execute("PRAGMA journal_mode=WAL")
                with db:
                    yield db
            finally:
                db.close()

    @contextmanager
    def transaction(self, tenant_id: str):
        with self._connect() as db:
            if self.dsn:
                db.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
                db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (tenant_id,))
            else:
                db.execute("BEGIN IMMEDIATE")
            yield StateTransaction(db, tenant_id, bool(self.dsn))
