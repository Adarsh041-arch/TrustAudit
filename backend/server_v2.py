"""Audit V2 API Server — Port :8100 (PHASES_V2).

Exposes production FastAPI endpoints for Audit V2:
- Document Ingestion & VLM Extraction Fallback
- 3-Tier Correlation & 3-Way Match Audit
- Cryptographic Audit Log with Chain Verification
- Human Review Queue & Golden Set Feedback Loop
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from audit_v2.domain.adjudicator import AdjudicationRequest, Adjudicator
from audit_v2.domain.correlation import build_clusters, build_corpus_index
from audit_v2.domain.finding_generator import make_finding_from_result
from audit_v2.domain.models import (
    CheckCatalogEntry,
    CheckContext,
    DocumentType,
    ExtractedDocument,

    Finding,
    FindingStatus,
    Severity,
)
from audit_v2.domain.validators.duplicate import check_duplicate_document
from audit_v2.domain.validators.threeway import (
    check_cumulative_invoiced,
    check_invoiced_vs_received,
    check_price_matches_po,
    check_receipt_exists,
)

from audit_v2.orchestration.activities import extract_document
from audit_v2.orchestration.cluster_audit import ClusterAuditor
from audit_v2.orchestration.review_queue import ReviewAction, ReviewQueue
from audit_v2.persistence.audit_log import AuditLog
from audit_v2.persistence.permission_matrix import Action, Resource, Role, has_permission
from audit_v2.persistence.provenance import ProvenanceGraph
from audit_v2.domain.catalog_loader import load_catalog

CATALOG = load_catalog()
CATALOG_BY_ID = {c.check_id: c for c in CATALOG.checks}


logger = logging.getLogger(__name__)

app = FastAPI(title="Audit V2 API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage engines for API service session
AUDIT_LOG = AuditLog()
PROVENANCE = ProvenanceGraph()
REVIEW_QUEUE = ReviewQueue()
DOCUMENTS_STORE: dict[str, ExtractedDocument] = {}
FINDINGS_STORE: list[Finding] = []
CLUSTER_AUDITOR = ClusterAuditor(ruleset_version="ruleset_v2.0")

ADJUDICATOR = Adjudicator()


class ReviewRequestPayload(BaseModel):
    item_id: str
    reviewer_id: str = "auditor_1"
    reviewer_role: str = "reviewer"
    action: str  # confirm | reject_as_false_positive | escalate
    comments: str | None = None


@app.get("/api/v2/health")
def health_check() -> dict[str, Any]:
    valid, err = AUDIT_LOG.verify_chain()
    return {
        "status": "OK",
        "version": "2.0.0",
        "documents_count": len(DOCUMENTS_STORE),
        "findings_count": len(FINDINGS_STORE),
        "audit_log_entries": len(AUDIT_LOG.entries),
        "audit_log_valid": valid,
        "audit_log_error": err,
    }


@app.post("/api/v2/audit/upload")
async def upload_documents(
    files: list[UploadFile] = File(...),
    tenant_id: str = "tenant_default",
) -> dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for upload")

    ingested_docs: list[ExtractedDocument] = []
    extraction_results: list[dict[str, Any]] = []

    for file in files:
        data = await file.read()
        document_id = f"doc_{uuid.uuid4().hex[:8]}"
        mime_type = file.content_type or "application/pdf"

        res = extract_document(
            data=data,
            document_id=document_id,
            tenant_id=tenant_id,
            mime_type=mime_type,
        )

        if res.error or res.document is None:
            logger.warning("Failed to extract file %s: %s", file.filename, res.error)
            continue

        doc = res.document
        DOCUMENTS_STORE[doc.document_id] = doc
        ingested_docs.append(doc)
        extraction_results.append({
            "filename": file.filename,
            "document_id": doc.document_id,
            "doc_type": doc.doc_type.value,
            "is_vlm_fallback": doc.extractor_version.startswith("vlm"),
            "extractor_version": doc.extractor_version,
            "pages": doc.page_count,
        })

        AUDIT_LOG.log(
            entry_id=f"log_{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            action="document_ingested",
            resource_type=Resource.DOCUMENT,
            resource_id=doc.document_id,
            actor_id="system",
            payload={
                "filename": file.filename,
                "doc_type": doc.doc_type.value,
                "extractor_version": doc.extractor_version,
                "pages": doc.page_count,
            },
        )

    if not ingested_docs:
        raise HTTPException(status_code=400, detail="Failed to extract any uploaded documents")

    # Perform cluster correlation & three-way match across entire updated corpus
    all_docs = list(DOCUMENTS_STORE.values())
    clusters = build_clusters(all_docs)
    corpus_index = build_corpus_index(all_docs)

    batch_findings: list[Finding] = []

    for doc in ingested_docs:
        target_cluster = None
        for c in clusters:
            if any(d.document_id == doc.document_id for d in c.documents):
                target_cluster = c
                break

        if target_cluster is not None:
            results = []
            if doc.doc_type == DocumentType.INVOICE:
                for check_id, validator_fn in [
                    ("CHK-XDOC-QTY-001", check_invoiced_vs_received),
                    ("CHK-XDOC-PRICE-001", check_price_matches_po),
                    ("CHK-XDOC-RECEIPT-001", check_receipt_exists),
                    ("CHK-XDOC-CUMUL-001", check_cumulative_invoiced),
                    ("CHK-DUP-DOC-001", check_duplicate_document),
                ]:
                    entry = CATALOG_BY_ID.get(check_id)
                    if entry is not None:
                        ctx = CheckContext(
                            document=doc,
                            check_entry=entry,
                            cluster=target_cluster,
                            corpus_index=corpus_index,
                        )
                        results.append(validator_fn(ctx))

            for r in results:
                if r.status != FindingStatus.SKIPPED:
                    entry = CATALOG_BY_ID.get(r.check_id) or CheckCatalogEntry(
                        check_id=r.check_id,
                        name=r.check_id,
                        description=r.message,
                        category="three_way_match",
                        applies_to=[doc.doc_type],
                        determinism="deterministic",
                        severity=Severity.HIGH,
                    )

                    finding = make_finding_from_result(
                        result=r,
                        check_entry=entry,
                        document=doc,
                        ruleset_version="ruleset_v2.0",
                        prompt_version="prompt_v1.0",
                        model_version="vlm_nvidia",
                    )
                    batch_findings.append(finding)
                    FINDINGS_STORE.append(finding)

                    PROVENANCE.record_finding_provenance(
                        finding=finding,
                        document_id=doc.document_id,
                        ruleset_version="ruleset_v2.0",
                        prompt_version="prompt_v1.0",
                        model_version="vlm_nvidia",
                    )

                    if finding.status == FindingStatus.FAIL or finding.requires_human_review:
                        val = float(doc.header.grand_total.decimal_value) if doc.header.grand_total else 0.0
                        REVIEW_QUEUE.enqueue(
                            finding=finding,
                            document_id=doc.document_id,
                            tenant_id=tenant_id,
                            total_value=val,
                        )

                    AUDIT_LOG.log(
                        entry_id=f"log_{uuid.uuid4().hex[:8]}",
                        tenant_id=tenant_id,
                        action="finding_emitted",
                        resource_type=Resource.FINDING,
                        resource_id=finding.finding_id,
                        actor_id="system",
                        payload={
                            "check_id": finding.check_id,
                            "status": finding.status.value,
                            "fingerprint": finding.decision_fingerprint,
                        },
                    )

    first_doc = ingested_docs[0].model_dump() if ingested_docs else None

    return {
        "message": f"Successfully ingested batch of {len(ingested_docs)} document(s)",
        "count": len(ingested_docs),
        "documents": [d.model_dump() for d in ingested_docs],
        "document": first_doc,
        "extraction_results": extraction_results,
        "findings": [f.model_dump() for f in batch_findings],
        "is_vlm_fallback": any(d.extractor_version.startswith("vlm") for d in ingested_docs),
    }



@app.get("/api/v2/audit/findings")
def list_findings(tenant_id: str = "tenant_default") -> dict[str, Any]:
    findings_data = [f.model_dump() for f in FINDINGS_STORE]
    return {
        "tenant_id": tenant_id,
        "count": len(findings_data),
        "findings": findings_data,
    }


@app.get("/api/v2/audit/log")
def get_audit_log(tenant_id: str = "tenant_default") -> dict[str, Any]:
    valid, err = AUDIT_LOG.verify_chain()
    entries_data = [
        {
            "entry_id": e.entry_id,
            "action": e.action,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "actor_id": e.actor_id,
            "payload": e.payload,
            "timestamp": e.timestamp,
            "prev_hash": e.prev_hash,
            "hash_chain": e.hash_chain,
        }
        for e in AUDIT_LOG.entries
    ]
    return {
        "tenant_id": tenant_id,
        "chain_valid": valid,
        "verification_error": err,
        "entries": entries_data,
    }


@app.get("/api/v2/audit/review-queue")
def get_review_queue() -> dict[str, Any]:
    pending = [
        {
            "item_id": item.item_id,
            "document_id": item.document_id,
            "priority_score": item.priority_score,
            "finding": item.finding.model_dump(),
            "created_at": item.created_at,
            "status": item.status,
        }
        for item in REVIEW_QUEUE.pending_items
    ]
    return {
        "count": len(pending),
        "pending_items": pending,
        "golden_set_candidates_count": len(REVIEW_QUEUE.golden_set_candidates),
    }


@app.post("/api/v2/audit/review")
def submit_review(payload: ReviewRequestPayload) -> dict[str, Any]:
    try:
        action_enum = ReviewAction(payload.action)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid review action: {payload.action}")

    try:
        item = REVIEW_QUEUE.submit_review(
            item_id=payload.item_id,
            reviewer_id=payload.reviewer_id,
            action=action_enum,
            comments=payload.comments,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Record in audit log
    AUDIT_LOG.log(
        entry_id=f"log_{uuid.uuid4().hex[:8]}",
        tenant_id="tenant_default",
        action=f"review_{action_enum.value}",
        resource_type=Resource.FINDING,
        resource_id=item.finding.finding_id,
        actor_id=payload.reviewer_id,
        payload={"action": action_enum.value, "comments": payload.comments},
    )

    return {
        "message": f"Review submitted for item {payload.item_id}",
        "status": item.status,
        "golden_set_candidates_total": len(REVIEW_QUEUE.golden_set_candidates),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
