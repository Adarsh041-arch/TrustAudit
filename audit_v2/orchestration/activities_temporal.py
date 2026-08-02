"""Temporal activity definitions for the audit workflow.

Each IO-bound step in the pipeline becomes a Temporal activity with
retry policies matching the §3.3 failure classification (policies are
defined on the workflow side, `temporal_workflow.py`).

Activities are stateless — the DocumentStore is injected via a module
global set by the worker (`set_activity_store`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from temporalio import activity

from audit_v2.domain.models import (
    DocumentStatus,
    ExtractedDocument,
    FailureClass,
    Finding,
)
from audit_v2.extraction.classifier import classify_document_from_data
from audit_v2.ingestion.dedup import compute_content_hash
from audit_v2.ingestion.document_store import DocumentStore
from audit_v2.orchestration.activities import (
    check_dedup,
    extract_document,
    normalize_document,
    process_pdf_pages,
    transition_document,
    validate_document,
)
from audit_v2.orchestration.workflows import run_checks_and_emit
from audit_v2.security.injection_detector import scan_document

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared context: the worker injects a DocumentStore here on startup.
# ---------------------------------------------------------------------------
_store: DocumentStore | None = None


def set_activity_store(store: DocumentStore) -> None:
    global _store
    _store = store


def _get_store() -> DocumentStore:
    if _store is None:
        raise RuntimeError("DocumentStore not injected into Temporal activity context")
    return _store


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class FetchDocumentInput:
    document_id: str
    tenant_id: str


@dataclass
class FetchDocumentResult:
    record: dict | None = None
    error: str | None = None


@activity.defn
async def fetch_document(input: FetchDocumentInput) -> FetchDocumentResult:
    store = _get_store()
    doc = store.get(input.document_id)
    if doc is None:
        return FetchDocumentResult(error=f"Document {input.document_id} not found")
    return FetchDocumentResult(record={
        "document_id": doc.document_id,
        "tenant_id": doc.tenant_id,
        "content_hash": doc.content_hash,
        "status": doc.status,
        "doc_type": doc.doc_type,
        "batch_id": doc.batch_id,
        "page_count": doc.page_count,
        "source_uri": doc.source_uri,
        "duplicate_of": doc.duplicate_of,
    })


@dataclass
class ValidateInput:
    document_id: str
    tenant_id: str
    data: bytes
    mime_type: str
    file_size: int


@dataclass
class ValidateResult:
    valid: bool
    error: str | None = None
    quarantine_type: str | None = None
    failure_class: FailureClass | None = None
    content_hash: str = ""
    duplicate_of: str | None = None


@activity.defn
async def validate_and_dedup(input: ValidateInput) -> ValidateResult:
    store = _get_store()

    content_hash = compute_content_hash(input.data)

    dedup_result = check_dedup(store, input.tenant_id, content_hash)
    if dedup_result is not None and dedup_result.document_id != input.document_id:
        return ValidateResult(
            valid=False,
            error=f"Duplicate of {dedup_result.document_id}",
            quarantine_type="DUPLICATE",
            duplicate_of=dedup_result.document_id,
        )

    validation = validate_document(input.data, input.mime_type, input.file_size)
    if not validation.valid:
        # Encrypted, corrupt, oversize, and unsupported-MIME inputs all fail
        # deterministically on retry — poison-pill per §3.3, never TRANSIENT.
        qt = validation.quarantine_type or "QUARANTINED"
        store.update_status(input.document_id, qt)
        return ValidateResult(
            valid=False,
            error=validation.error,
            quarantine_type=qt,
            failure_class=FailureClass.POISON,
            content_hash=content_hash,
        )

    transition_document(
        store, input.document_id,
        DocumentStatus.RECEIVED, DocumentStatus.VALIDATED,
    )
    return ValidateResult(valid=True, content_hash=content_hash)


@dataclass
class ProcessPdfInput:
    document_id: str
    data: bytes


@dataclass
class ProcessPdfResult:
    page_count: int = 0
    has_text_layer: bool = False
    error: str | None = None


@activity.defn
async def process_pdf_activity(input: ProcessPdfInput) -> ProcessPdfResult:
    result = process_pdf_pages(input.data)
    if result.get("error"):
        _get_store().update_status(input.document_id, "QUARANTINED")
        return ProcessPdfResult(error=result["error"])
    return ProcessPdfResult(
        page_count=result.get("page_count", 0),
        has_text_layer=result.get("has_text_layer", False),
    )


@dataclass
class ExtractInput:
    document_id: str
    tenant_id: str
    data: bytes
    mime_type: str


@dataclass
class ExtractResult:
    document: ExtractedDocument | None = None
    error: str | None = None
    raw_text: str = ""


@activity.defn
async def extract_activity(input: ExtractInput) -> ExtractResult:
    detected_type, _ = classify_document_from_data(input.data, input.mime_type)
    extraction = extract_document(
        input.data, input.mime_type, input.document_id, input.tenant_id,
        doc_type=detected_type,
    )
    if extraction.error is not None or extraction.document is None:
        _get_store().update_status(input.document_id, "FAILED")
        return ExtractResult(
            error=extraction.error or "Extraction returned None",
        )
    normalized = normalize_document(extraction.document)
    return ExtractResult(
        document=normalized,
        raw_text=extraction.text,
    )


@dataclass
class SecurityScanInput:
    document_id: str
    raw_text: str
    data: bytes


@dataclass
class SecurityScanResult:
    is_suspicious: bool = False
    summary: str = ""


@activity.defn
async def security_scan_activity(input: SecurityScanInput) -> SecurityScanResult:
    scan = scan_document(input.raw_text, input.data)
    if scan.is_suspicious:
        _get_store().update_status(
            input.document_id, DocumentStatus.QUARANTINED_SECURITY,
        )
    return SecurityScanResult(
        is_suspicious=scan.is_suspicious,
        summary=scan.summary(),
    )


@dataclass
class ValidateAndEmitInput:
    tenant_policy: str
    ruleset_version: str
    prompt_version: str
    model_version: str
    document: ExtractedDocument


@dataclass
class ValidateAndEmitResult:
    findings: list[Finding] = field(default_factory=list)
    routing_rule_id: str | None = None
    coverage_complete: bool = False
    error: str | None = None


@activity.defn
async def validate_and_emit_activity(
    input: ValidateAndEmitInput,
) -> ValidateAndEmitResult:
    """Route, run deterministic checks, and emit findings.

    Delegates to the same `run_checks_and_emit` the plain workflow uses,
    so the two execution paths cannot drift.
    """
    try:
        findings, routing = run_checks_and_emit(
            input.document,
            tenant_policy=input.tenant_policy,
            ruleset_version=input.ruleset_version,
            prompt_version=input.prompt_version,
            model_version=input.model_version,
        )
        return ValidateAndEmitResult(
            findings=findings,
            routing_rule_id=routing.rule_id,
            coverage_complete=input.document.coverage.coverage_complete,
        )
    except Exception as e:
        logger.exception("validate_and_emit failed")
        return ValidateAndEmitResult(error=str(e))


@dataclass
class PersistResultInput:
    document_id: str
    findings: list[Finding]
    status: str
    error: str | None = None


@activity.defn
async def persist_results_activity(input: PersistResultInput) -> None:
    store = _get_store()
    store.update_status(input.document_id, input.status)
