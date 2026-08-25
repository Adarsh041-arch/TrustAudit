from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from audit_v2.domain.adjudicator import AdjudicationRequest, Adjudicator
from audit_v2.domain.catalog_loader import entries_by_id, load_catalog
from audit_v2.domain.finding_generator import make_finding_from_result
from audit_v2.domain.models import (
    CheckDeterminism,
    DocumentStatus,
    ExtractedDocument,
    FailureClass,
    Finding,
)
from audit_v2.domain.validation import CheckRunner
from audit_v2.extraction.classifier import classify_document_from_data
from audit_v2.ingestion.dedup import compute_content_hash
from audit_v2.ingestion.document_store import DocumentStore, MemoryDocumentStore
from audit_v2.orchestration.activities import (
    check_dedup,
    extract_document,
    normalize_document,
    process_pdf_pages,
    transition_document,
    validate_document,
)
from audit_v2.routing.engine import resolve
from audit_v2.security.injection_detector import scan_document

logger = logging.getLogger(__name__)


def run_checks_and_emit(
    normalized,
    tenant_policy: str,
    ruleset_version: str,
    prompt_version: str,
    model_version: str,
    current_date: date | None = None,
):
    """Route the document, run deterministic checks, and emit findings.

    Shared by the plain `AuditWorkflow` and the Temporal
    `validate_and_emit_activity` so the two paths cannot drift.
    Returns `(findings, routing_decision)`.
    """
    doc_type = normalized.doc_type
    total_value = None
    if normalized.header.grand_total is not None:
        total_value = Decimal(normalized.header.grand_total.value)

    catalog = load_catalog()
    by_id = entries_by_id(catalog)

    # Only deterministic checks are dispatched here. model_assisted
    # checks belong to the Phase 8 adjudicator.
    catalog_check_ids = [
        c.check_id
        for c in catalog.checks
        if c.determinism == CheckDeterminism.DETERMINISTIC
        and doc_type in c.applies_to
    ]
    routing_decision = resolve(
        doc_type, total_value, tenant_policy, catalog_check_ids,
    )
    logger.info(
        "Routing %s: rule=%s included=%d skipped=%d",
        normalized.document_id, routing_decision.rule_id,
        len(routing_decision.included_check_ids),
        len(routing_decision.skipped_check_ids),
    )

    runner = CheckRunner(catalog_checks=catalog.checks)
    findings: list[Finding] = []
    check_results = runner.run_all(
        document=normalized,
        included_check_ids=routing_decision.included_check_ids,
        skipped_check_ids=routing_decision.skipped_check_ids,
        current_date=current_date,
    )
    for cr in check_results:
        entry = by_id.get(cr.check_id)
        if entry is None:
            continue
        finding = make_finding_from_result(
            result=cr,
            check_entry=entry,
            document=normalized,
            ruleset_version=ruleset_version,
            prompt_version=prompt_version,
            model_version=model_version,
        )
        findings.append(finding)

    return findings, routing_decision


@dataclass
class AuditWorkflowInput:
    document_id: str
    tenant_id: str
    ruleset_version: str
    data: bytes | None = None
    mime_type: str | None = None
    file_size: int | None = None
    prompt_version: str = "prompt_v3"
    model_version: str = "gemini-2.5-flash"
    tenant_policy: str = "standard"
    current_date: date | str | None = None


@dataclass
class AuditWorkflowOutput:
    document_id: str
    finding_ids: list[str]
    status: str
    findings: list[Finding] = field(default_factory=list)
    duplicate_of: str | None = None
    error: str | None = None
    routing_rule_id: str | None = None
    failure_class: FailureClass | None = None
    document: ExtractedDocument | None = None
    requires_human_review: bool = False


class AuditWorkflow:
    def __init__(self, store: DocumentStore | None = None):
        self._store = store or MemoryDocumentStore()

    async def run(self, inp: AuditWorkflowInput) -> AuditWorkflowOutput:
        store = self._store
        doc = store.get(inp.document_id)
        if doc is None:
            return AuditWorkflowOutput(
                document_id=inp.document_id,
                finding_ids=[],
                status="FAILED",
                error="Document not found",
            )

        try:
            if inp.data is not None and inp.mime_type is not None and inp.file_size is not None:
                content_hash = compute_content_hash(inp.data)
                dedup_result = check_dedup(store, inp.tenant_id, content_hash)
                if dedup_result is not None and dedup_result.document_id != inp.document_id:
                    return AuditWorkflowOutput(
                        document_id=inp.document_id,
                        finding_ids=[],
                        status="DUPLICATE",
                        duplicate_of=dedup_result.document_id,
                    )

                validation = validate_document(inp.data, inp.mime_type, inp.file_size)
                if not validation.valid:
                    qt = validation.quarantine_type or "QUARANTINED"
                    store.update_status(inp.document_id, qt)
                    return AuditWorkflowOutput(
                        document_id=inp.document_id,
                        finding_ids=[],
                        status=qt,
                        error=validation.error,
                    )

                transition_document(
                    store, inp.document_id,
                    DocumentStatus.RECEIVED, DocumentStatus.VALIDATED,
                )

                if inp.mime_type == "application/pdf":
                    pdf_info = process_pdf_pages(inp.data)
                    if pdf_info.get("error"):
                        store.update_status(inp.document_id, "QUARANTINED")
                        return AuditWorkflowOutput(
                            document_id=inp.document_id,
                            finding_ids=[],
                            status="QUARANTINED",
                            error=pdf_info["error"],
                        )

                    for from_s, to_s in [
                        (DocumentStatus.VALIDATED, DocumentStatus.SCANNED),
                        (DocumentStatus.SCANNED, DocumentStatus.RENDERED),
                    ]:
                        transition_document(store, inp.document_id, from_s, to_s)

                    transition_document(
                        store, inp.document_id,
                        DocumentStatus.RENDERED, DocumentStatus.EXTRACTED,
                    )
                else:
                    transition_document(
                        store, inp.document_id,
                        DocumentStatus.VALIDATED, DocumentStatus.EXTRACTED,
                    )

                detected_type, type_confidence = classify_document_from_data(
                    inp.data, inp.mime_type,
                )
                logger.info(
                    "Classified %s as %s (confidence %.2f)",
                    inp.document_id, detected_type.value, type_confidence,
                )
                extraction = extract_document(
                    inp.data, inp.mime_type, inp.document_id, inp.tenant_id,
                    doc_type=detected_type,
                )
                if extraction.error is not None or extraction.document is None:
                    store.update_status(inp.document_id, "FAILED")
                    return AuditWorkflowOutput(
                        document_id=inp.document_id,
                        finding_ids=[],
                        status="FAILED",
                        error=extraction.error or "Extraction returned None",
                    )

                transition_document(
                    store, inp.document_id,
                    DocumentStatus.EXTRACTED, DocumentStatus.NORMALIZED,
                )
                normalized = normalize_document(extraction.document)

                # PHASES_V2 §5: untrusted content is scanned before any finding is
                # issued. A flagged document is never reported as PASS.
                scan = scan_document(extraction.text or "", inp.data)
                if scan.is_suspicious:
                    logger.warning(
                        "Quarantining %s for security: %s",
                        inp.document_id, scan.summary(),
                    )
                    store.update_status(
                        inp.document_id, DocumentStatus.QUARANTINED_SECURITY,
                    )
                    return AuditWorkflowOutput(
                        document_id=inp.document_id,
                        finding_ids=[],
                        status=DocumentStatus.QUARANTINED_SECURITY,
                        error=f"Prompt-injection scan failed: {scan.summary()}",
                        failure_class=FailureClass.POLICY,
                    )

                # Resolve current_date
                current_date_val = None
                if inp.current_date:
                    if isinstance(inp.current_date, str):
                        from datetime import datetime
                        try:
                            current_date_val = datetime.strptime(inp.current_date, "%Y-%m-%d").date()
                        except ValueError:
                            pass
                    elif isinstance(inp.current_date, date):
                        current_date_val = inp.current_date

                stored_findings, routing_decision = run_checks_and_emit(
                    normalized,
                    tenant_policy=inp.tenant_policy,
                    ruleset_version=inp.ruleset_version,
                    prompt_version=inp.prompt_version,
                    model_version=inp.model_version,
                    current_date=current_date_val,
                )

                # PHASES_V2 §4 Phase 8: extractor disagreement routes to human
                # review. The adjudicator may never overturn deterministic
                # verdicts; it only flags the disagreement.
                requires_human_review = bool(normalized.extraction_disagreements)
                if requires_human_review:
                    adjudication = Adjudicator().adjudicate(AdjudicationRequest(
                        document_id=inp.document_id,
                        tenant_id=inp.tenant_id,
                        deterministic_findings=stored_findings,
                        extraction_disagreements=normalized.extraction_disagreements,
                    ))
                    requires_human_review = adjudication.requires_human_review

                # PHASES_V2 §3.5: a document whose pages were not all examined
                # cannot be reported as complete, regardless of findings.
                final_status = (
                    "READY" if normalized.coverage.coverage_complete else "INCOMPLETE"
                )
                store.update_status(inp.document_id, final_status)
                return AuditWorkflowOutput(
                    document_id=inp.document_id,
                    finding_ids=[f.finding_id for f in stored_findings],
                    findings=stored_findings,
                    status=final_status,
                    routing_rule_id=routing_decision.rule_id,
                    document=normalized,
                    requires_human_review=requires_human_review,
                )

            store.update_status(inp.document_id, "READY")
            return AuditWorkflowOutput(
                document_id=inp.document_id,
                finding_ids=[],
                status="READY",
            )

        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception as e:
            logger.exception("Workflow failed for %s", inp.document_id)
            store.update_status(inp.document_id, "FAILED")
            return AuditWorkflowOutput(
                document_id=inp.document_id,
                finding_ids=[],
                status="FAILED",
                error=str(e),
                failure_class=FailureClass.LOGIC,
            )
