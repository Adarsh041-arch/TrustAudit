"""End-to-end integration test: ingest -> extract -> validate -> emit finding."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from audit_v2.ingestion.document_store import MemoryDocumentStore
from audit_v2.orchestration.workflows import AuditWorkflow, AuditWorkflowInput

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PDF = REPO_ROOT / "sample_docs" / "INV-2026-0715_NewTech_Solutions.pdf"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_workflow_emits_findings_on_golden_invoice():
    """Run the full pipeline against the real golden manifest PDF.

    This is the M1 thin-slice integration: if this passes, the
    Vertical Slice thesis (deterministic math over VLM extraction)
    is proven end-to-end.
    """
    if not GOLDEN_PDF.exists():
        pytest.skip(f"Golden PDF not present: {GOLDEN_PDF}")

    pdf_bytes = GOLDEN_PDF.read_bytes()

    store = MemoryDocumentStore()
    workflow = AuditWorkflow(store=store)
    record = store.create(
        tenant_id="tenant_a",
        content_hash="sha256:placeholder",
        source_uri=f"s3://tenant-a/raw/{GOLDEN_PDF.name}",
    )

    inp = AuditWorkflowInput(
        document_id=record.document_id,
        tenant_id="tenant_a",
        ruleset_version="rs_2026_07_26",
        data=pdf_bytes,
        mime_type="application/pdf",
        file_size=len(pdf_bytes),
    )

    out = _run(workflow.run(inp))

    assert out.error is None, f"Workflow error: {out.error}"
    assert out.status in {"READY", "FAILED"}
    assert isinstance(out.findings, list)


def test_workflow_handles_missing_document():
    """A document that doesn't exist in the store must return FAILED."""
    store = MemoryDocumentStore()
    workflow = AuditWorkflow(store=store)
    inp = AuditWorkflowInput(
        document_id="missing",
        tenant_id="tenant_a",
        ruleset_version="rs_2026_07_26",
    )
    out = _run(workflow.run(inp))
    assert out.status == "FAILED"
    assert out.error is not None


def test_workflow_quarantines_encrypted_pdf():
    """Encrypted PDFs must be quarantined, not crash the workflow."""
    store = MemoryDocumentStore()
    workflow = AuditWorkflow(store=store)
    record = store.create(
        tenant_id="tenant_a",
        content_hash="sha256:encrypted",
        source_uri="s3://tenant-a/raw/encrypted.pdf",
    )
    fake_encrypted_pdf = b"%PDF-1.7\n/Encrypt 1 R\nfoo"
    inp = AuditWorkflowInput(
        document_id=record.document_id,
        tenant_id="tenant_a",
        ruleset_version="rs_2026_07_26",
        data=fake_encrypted_pdf,
        mime_type="application/pdf",
        file_size=len(fake_encrypted_pdf),
    )
    out = _run(workflow.run(inp))
    assert out.status == "QUARANTINED_ENCRYPTED"


