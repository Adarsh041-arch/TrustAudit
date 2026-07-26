"""Golden-set generator + evaluation harness smoke test.

Generates a small in-memory corpus and asserts the pipeline detects every
seeded defect with zero false alarms — a fast proxy for the full 200-doc
run in evaluation/measure_v2.py.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from audit_v2.ingestion.document_store import MemoryDocumentStore
from audit_v2.orchestration.workflows import AuditWorkflow, AuditWorkflowInput
from evaluation.golden_set.generator import build_corpus


def _audit(pdf_bytes: bytes):
    store = MemoryDocumentStore()
    workflow = AuditWorkflow(store=store)
    record = store.create(
        tenant_id="golden", content_hash="sha256:x", source_uri="golden://t",
    )
    return asyncio.run(workflow.run(AuditWorkflowInput(
        document_id=record.document_id,
        tenant_id="golden",
        ruleset_version="rs_test",
        data=pdf_bytes,
        mime_type="application/pdf",
        file_size=len(pdf_bytes),
    )))


def test_generator_is_deterministic():
    a = build_corpus(6, 3, seed=7)
    b = build_corpus(6, 3, seed=7)
    assert [d.document_id for d in a] == [d.document_id for d in b]
    assert [d.pdf_bytes for d in a] == [d.pdf_bytes for d in b]
    assert [d.expected_findings for d in a] == [d.expected_findings for d in b]


def test_seeded_defects_are_detected_without_false_alarms():
    docs = build_corpus(12, 4, seed=99)
    assert any(d.defects for d in docs), "corpus must contain defective docs"

    for doc in docs:
        out = _audit(doc.pdf_bytes)
        assert out.error is None, f"{doc.document_id}: {out.error}"
        assert out.status == "READY", f"{doc.document_id}: status {out.status}"

        emitted_fails = {
            f.check_id for f in out.findings
            if str(getattr(f.status, "value", f.status)) == "FAIL"
        }
        gold_fails = {ef["check_id"] for ef in doc.expected_findings}

        missed = gold_fails - emitted_fails
        assert not missed, (
            f"{doc.document_id} (defects={doc.defects}): missed {missed}"
        )
        false_alarms = emitted_fails - gold_fails
        assert not false_alarms, (
            f"{doc.document_id} (defects={doc.defects}): false alarms {false_alarms}"
        )
