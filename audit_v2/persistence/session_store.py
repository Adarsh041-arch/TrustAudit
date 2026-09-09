"""Durable, append-only audit session and layer trace storage."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from audit_v2.pipeline.events import ProgressSink, StepEvent


def _json(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, default=str, ensure_ascii=False)


class AuditSessionStore:
    """SQLite ledger. Rows are inserted, never updated except session completion."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.getenv("AUDIT_SESSION_DB") or ".data/audit_sessions.sqlite3"
        self.path = Path(configured)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS audit_sessions (
                    session_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, completed_at TEXT,
                    status TEXT NOT NULL, result_json TEXT
                );
                CREATE TABLE IF NOT EXISTS session_documents (
                    session_id TEXT NOT NULL, document_id TEXT NOT NULL,
                    filename TEXT NOT NULL, mime_type TEXT NOT NULL,
                    content_hash TEXT NOT NULL, original_bytes BLOB,
                    canonical_json TEXT, result_json TEXT,
                    PRIMARY KEY(session_id, document_id),
                    FOREIGN KEY(session_id) REFERENCES audit_sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS layer_runs (
                    layer_run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    document_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                    layer TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, detail TEXT,
                    payload_json TEXT, parent_layer_run_id TEXT,
                    FOREIGN KEY(session_id) REFERENCES audit_sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_tenant
                    ON audit_sessions(tenant_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_layers_document
                    ON layer_runs(session_id, document_id, sequence);
            """)

    def create_session(self, tenant_id: str) -> str:
        session_id = f"session_{uuid.uuid4().hex[:16]}"
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO audit_sessions VALUES (?, ?, ?, NULL, 'RUNNING', NULL)",
                (session_id, tenant_id, datetime.now(UTC).isoformat()),
            )
        return session_id

    def record_document(
        self, session_id: str, document_id: str, filename: str,
        mime_type: str, data: bytes, canonical: Any, result: Any,
    ) -> None:
        keep_original = os.getenv("AUDIT_STORE_ORIGINALS", "true").lower() == "true"
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO session_documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, document_id, filename, mime_type,
                 hashlib.sha256(data).hexdigest(), data if keep_original else None,
                 _json(canonical), _json(result)),
            )

    def record_layer(
        self, session_id: str, document_id: str, sequence: int,
        layer: str, status: str, detail: str = "", payload: Any = None,
        parent_layer_run_id: str | None = None,
    ) -> str:
        layer_id = f"layer_{uuid.uuid4().hex[:16]}"
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO layer_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (layer_id, session_id, document_id, sequence, layer, status,
                 datetime.now(UTC).isoformat(), detail, _json(payload or {}),
                 parent_layer_run_id),
            )
        return layer_id

    def complete(self, session_id: str, result: Any, status: str = "COMPLETED") -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE audit_sessions SET completed_at=?, status=?, result_json=? "
                "WHERE session_id=?",
                (datetime.now(UTC).isoformat(), status, _json(result), session_id),
            )

    def list_sessions(self, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT s.*, COUNT(d.document_id) document_count FROM audit_sessions s "
                "LEFT JOIN session_documents d ON d.session_id=s.session_id "
                "WHERE s.tenant_id=? GROUP BY s.session_id ORDER BY s.created_at DESC LIMIT ?",
                (tenant_id, min(max(limit, 1), 200)),
            ).fetchall()
        return [dict(row) | {"result_json": None} for row in rows]

    def get_session(self, session_id: str, tenant_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM audit_sessions WHERE session_id=? AND tenant_id=?",
                (session_id, tenant_id),
            ).fetchone()
            if row is None:
                return None
            documents = db.execute(
                "SELECT document_id, filename, mime_type, content_hash, result_json "
                "FROM session_documents WHERE session_id=? ORDER BY rowid",
                (session_id,),
            ).fetchall()
        value = dict(row)
        value["result"] = json.loads(value.pop("result_json") or "null")
        value["documents"] = [
            dict(item) | {"result": json.loads(item["result_json"] or "null")}
            for item in documents
        ]
        for item in value["documents"]:
            item.pop("result_json", None)
        return value

    def trace(self, session_id: str, document_id: str, tenant_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            allowed = db.execute(
                "SELECT 1 FROM audit_sessions WHERE session_id=? AND tenant_id=?",
                (session_id, tenant_id),
            ).fetchone()
            doc = db.execute(
                "SELECT filename, mime_type, content_hash, canonical_json, result_json "
                "FROM session_documents WHERE session_id=? AND document_id=?",
                (session_id, document_id),
            ).fetchone()
            if allowed is None or doc is None:
                return None
            rows = db.execute(
                "SELECT * FROM layer_runs WHERE session_id=? AND document_id=? "
                "ORDER BY sequence, created_at",
                (session_id, document_id),
            ).fetchall()
        return {
            "session_id": session_id, "document_id": document_id,
            "filename": doc["filename"], "mime_type": doc["mime_type"],
            "content_hash": doc["content_hash"],
            "canonical": json.loads(doc["canonical_json"] or "null"),
            "result": json.loads(doc["result_json"] or "null"),
            "layers": [dict(row) | {
                "payload": json.loads(row["payload_json"] or "{}")
            } for row in rows],
        }


class RecordingSink:
    """Thread-safe progress sink that persists all pipeline passes."""

    def __init__(self, store: AuditSessionStore, session_id: str, delegate: ProgressSink) -> None:
        self.store, self.session_id, self.delegate = store, session_id, delegate
        self._lock = threading.Lock()
        self._sequence: dict[str, int] = {}

    def emit(self, event: StepEvent) -> None:
        self.delegate.emit(event)
        with self._lock:
            sequence = self._sequence.get(event.document_id, 0) + 1
            self._sequence[event.document_id] = sequence
        self.store.record_layer(
            self.session_id, event.document_id, sequence, event.step.value,
            event.status.value, event.detail, event.data,
        )

    def next_sequence(self, document_id: str) -> int:
        with self._lock:
            sequence = self._sequence.get(document_id, 0) + 1
            self._sequence[document_id] = sequence
            return sequence
