"""Minimal findings persistence: insert + list by document.

Called from run_checks_and_emit() when a Postgres connection is configured;
otherwise findings stay in-memory as before.
"""
from __future__ import annotations

import json

from audit_v2.persistence.db import tenant_session


class FindingStore:
    def __init__(self, conn, tenant_id: str):
        self._conn = conn
        self._tenant_id = tenant_id

    def insert(self, finding) -> None:
        """Insert one finding (domain Finding model or equivalent dict)."""
        f = finding if isinstance(finding, dict) else finding.model_dump(mode="json")
        with tenant_session(self._conn, self._tenant_id) as conn:
            conn.execute(
                "INSERT INTO findings (finding_id, tenant_id, document_id, check_id,"
                " verdict, severity, expected_value, actual_value, discrepancy,"
                " evidence, decision_fingerprint, supersedes, engine_version)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (tenant_id, document_id, check_id, decision_fingerprint)"
                " DO NOTHING",
                (
                    f["finding_id"],
                    self._tenant_id,
                    f["document_id"],
                    f["check_id"],
                    f.get("status", f.get("verdict")),
                    f.get("severity"),
                    _text(f.get("expected", f.get("expected_value"))),
                    _text(f.get("actual", f.get("actual_value"))),
                    _text(f.get("delta", f.get("discrepancy"))),
                    json.dumps(f.get("evidence") or {}),
                    f["decision_fingerprint"],
                    f.get("supersedes"),
                    f.get("ruleset_version", f.get("engine_version")),
                ),
            )

    def list_by_document(self, document_id: str) -> list[dict]:
        with tenant_session(self._conn, self._tenant_id) as conn:
            rows = conn.execute(
                "SELECT finding_id, check_id, verdict, severity, expected_value,"
                " actual_value, discrepancy, evidence, decision_fingerprint, supersedes"
                " FROM findings WHERE document_id = %s ORDER BY finding_id",
                (document_id,),
            ).fetchall()
        cols = (
            "finding_id", "check_id", "verdict", "severity", "expected_value",
            "actual_value", "discrepancy", "evidence", "decision_fingerprint", "supersedes",
        )
        return [dict(zip(cols, r, strict=False)) for r in rows]



def _text(v) -> str | None:
    return None if v is None else str(v)
