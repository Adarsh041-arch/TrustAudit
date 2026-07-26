"""Determinism gate — PHASES_V2 §2.

Same document + same ruleset_version + same model_version must produce the same
findings set on >=98% of re-runs. Evidence prose may vary; verdicts may not.

The deterministic path has no model call, so agreement must be exactly 1.00 —
any drift here is a bug (unstable iteration order, dict ordering, time
dependence), not model nondeterminism.
"""
import asyncio
from pathlib import Path

import pytest

from audit_v2.ingestion.document_store import MemoryDocumentStore
from audit_v2.orchestration.workflows import AuditWorkflow, AuditWorkflowInput

GOLDEN_PDF = (
    Path(__file__).resolve().parents[1]
    / "sample_docs" / "INV-2026-0715_NewTech_Solutions.pdf"
)
REPEATS = 10


def _run_once(data: bytes, run_id: int):
    store = MemoryDocumentStore()
    rec = store.create(
        tenant_id="t1", content_hash=f"hash-{run_id}", source_uri="x", doc_type="invoice",
    )
    return asyncio.run(AuditWorkflow(store=store).run(AuditWorkflowInput(
        document_id=rec.document_id, tenant_id="t1", ruleset_version="rs_2026_07_26",
        data=data, mime_type="application/pdf", file_size=len(data),
    )))


@pytest.fixture(scope="module")
def golden_bytes():
    if not GOLDEN_PDF.exists():
        pytest.skip(f"Golden PDF not present: {GOLDEN_PDF}")
    return GOLDEN_PDF.read_bytes()


def test_verdict_set_is_stable_across_runs(golden_bytes):
    baseline = None
    for i in range(REPEATS):
        out = _run_once(golden_bytes, i)
        verdicts = frozenset((f.check_id, str(f.status)) for f in out.findings)
        if baseline is None:
            baseline = verdicts
            continue
        assert verdicts == baseline, (
            f"Run {i} disagreed with run 0.\n"
            f"Only in run {i}: {sorted(verdicts - baseline)}\n"
            f"Only in run 0: {sorted(baseline - verdicts)}"
        )


def test_status_and_routing_are_stable(golden_bytes):
    outs = [_run_once(golden_bytes, i) for i in range(5)]
    assert len({o.status for o in outs}) == 1
    assert len({o.routing_rule_id for o in outs}) == 1


def test_decision_fingerprint_is_stable(golden_bytes):
    """§3.6: two runs of the same inputs must agree, and the fingerprint proves it."""
    first = {
        f.check_id: f.decision_fingerprint for f in _run_once(golden_bytes, 0).findings
    }
    for i in range(1, 5):
        again = {
            f.check_id: f.decision_fingerprint for f in _run_once(golden_bytes, i).findings
        }
        assert again == first, f"Fingerprints drifted on run {i}"


def test_fingerprint_changes_when_ruleset_changes(golden_bytes):
    """A different fingerprint is what explains why a re-run differs."""
    store = MemoryDocumentStore()
    rec = store.create(
        tenant_id="t1", content_hash="h-rs", source_uri="x", doc_type="invoice",
    )
    out_a = asyncio.run(AuditWorkflow(store=store).run(AuditWorkflowInput(
        document_id=rec.document_id, tenant_id="t1", ruleset_version="rs_A",
        data=golden_bytes, mime_type="application/pdf", file_size=len(golden_bytes),
    )))

    store_b = MemoryDocumentStore()
    rec_b = store_b.create(
        tenant_id="t1", content_hash="h-rs2", source_uri="x", doc_type="invoice",
    )
    out_b = asyncio.run(AuditWorkflow(store=store_b).run(AuditWorkflowInput(
        document_id=rec_b.document_id, tenant_id="t1", ruleset_version="rs_B",
        data=golden_bytes, mime_type="application/pdf", file_size=len(golden_bytes),
    )))

    fp_a = {f.check_id: f.decision_fingerprint for f in out_a.findings}
    fp_b = {f.check_id: f.decision_fingerprint for f in out_b.findings}
    shared = set(fp_a) & set(fp_b)
    assert shared, "expected overlapping checks between the two runs"
    assert all(fp_a[c] != fp_b[c] for c in shared), (
        "ruleset_version must be part of the fingerprint"
    )
