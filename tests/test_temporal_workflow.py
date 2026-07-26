"""Temporal workflow integration tests using WorkflowEnvironment.

`start_time_skipping()` downloads the Temporal test-server binary on first
run; when that is impossible (offline CI), the affected tests skip rather
than fail.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from audit_v2.ingestion.document_store import MemoryDocumentStore
from audit_v2.orchestration.activities_temporal import (
    ValidateAndEmitInput,
    extract_activity,
    fetch_document,
    persist_results_activity,
    process_pdf_activity,
    security_scan_activity,
    set_activity_store,
    validate_and_dedup,
    validate_and_emit_activity,
)
from audit_v2.orchestration.temporal_workflow import (
    AuditDocumentWorkflow,
    AuditWorkflowInput,
    AuditWorkflowOutput,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PDF = REPO_ROOT / "sample_docs" / "INV-2026-0715_NewTech_Solutions.pdf"


async def _run_workflow(
    inp: AuditWorkflowInput,
    *,
    store: MemoryDocumentStore | None = None,
) -> AuditWorkflowOutput:
    if store is None:
        store = MemoryDocumentStore()
    set_activity_store(store)
    try:
        env = await WorkflowEnvironment.start_time_skipping()
    except RuntimeError as e:  # test-server binary unavailable (offline)
        pytest.skip(f"Temporal test server unavailable: {e}")
    async with env, Worker(
        env.client,
        task_queue="test-queue",
        workflows=[AuditDocumentWorkflow],
        activities=[
            fetch_document,
            validate_and_dedup,
            process_pdf_activity,
            extract_activity,
            security_scan_activity,
            validate_and_emit_activity,
            persist_results_activity,
        ],
    ):
        result: AuditWorkflowOutput = await env.client.execute_workflow(
            workflow=AuditDocumentWorkflow.run,
            arg=inp,
            id=f"test-{inp.document_id}",
            task_queue="test-queue",
        )
    return result


@pytest.mark.asyncio
async def test_missing_document_returns_failed():
    result = await _run_workflow(AuditWorkflowInput(
        document_id="nonexistent",
        tenant_id="tenant_a",
        ruleset_version="rs_test",
    ))
    assert result.status == "FAILED"
    assert result.error is not None


@pytest.mark.asyncio
async def test_quarantines_encrypted_pdf():
    store = MemoryDocumentStore()
    record = store.create(
        tenant_id="tenant_a",
        content_hash="sha256:encrypted",
        source_uri="s3://test/encrypted.pdf",
    )
    fake_pdf = b"%PDF-1.7\n/Encrypt 1 R\nfoobar"
    result = await _run_workflow(AuditWorkflowInput(
        document_id=record.document_id,
        tenant_id="tenant_a",
        ruleset_version="rs_test",
        data=fake_pdf,
        mime_type="application/pdf",
        file_size=len(fake_pdf),
    ), store=store)
    assert result.status in {"QUARANTINED_ENCRYPTED", "QUARANTINED"}
    assert result.error is not None


@pytest.mark.skipif(not GOLDEN_PDF.exists(), reason="Golden PDF not found")
@pytest.mark.asyncio
async def test_processes_golden_invoice():
    store = MemoryDocumentStore()
    pdf_bytes = GOLDEN_PDF.read_bytes()
    record = store.create(
        tenant_id="tenant_a",
        content_hash="sha256:placeholder",
        source_uri=f"s3://test/{GOLDEN_PDF.name}",
    )
    result = await _run_workflow(AuditWorkflowInput(
        document_id=record.document_id,
        tenant_id="tenant_a",
        ruleset_version="rs_test",
        data=pdf_bytes,
        mime_type="application/pdf",
        file_size=len(pdf_bytes),
    ), store=store)
    assert result.error is None, f"Workflow error: {result.error}"
    assert result.status == "READY"
    assert result.routing_rule_id == "ROUTE-INV-001"
    # Same document, same ruleset -> same verdicts as the plain workflow:
    # the golden invoice carries 3 known deterministic defects.
    statuses = [f["status"] if isinstance(f, dict) else f.status for f in result.findings]
    fail_count = sum(1 for s in statuses if str(getattr(s, "value", s)) == "FAIL")
    assert fail_count == 3, f"expected 3 FAILs, got {fail_count}"


@pytest.mark.asyncio
async def test_handles_no_data_gracefully():
    store = MemoryDocumentStore()
    record = store.create(
        tenant_id="tenant_a",
        content_hash="sha256:nodata",
    )
    result = await _run_workflow(AuditWorkflowInput(
        document_id=record.document_id,
        tenant_id="tenant_a",
        ruleset_version="rs_test",
    ), store=store)
    # No payload: same behavior as the plain AuditWorkflow — READY.
    assert result.status == "READY"
    assert result.error is None


@pytest.mark.asyncio
async def test_validate_and_emit_activity_error_path():
    """A malformed document must yield an error result, not raise or crash.

    Regression for `ValidateAndEmitResult.findings` defaulting to the `list`
    type instead of an instance, which broke every error-path construction.
    """
    result = await validate_and_emit_activity(ValidateAndEmitInput(
        tenant_policy="standard",
        ruleset_version="rs_test",
        prompt_version="p1",
        model_version="m1",
        document=None,  # type: ignore[arg-type] — deliberately malformed
    ))
    assert result.error is not None
    assert result.findings == []
    assert list(result.findings) == []  # iterable instance, not the type object
