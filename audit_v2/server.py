"""Audit V2 API Server — Port :8100 (PHASES_V2).

Exposes production FastAPI endpoints for Audit V2:
- Document Ingestion & VLM Extraction Fallback
- 3-Tier Correlation & 3-Way Match Audit
- Cryptographic Audit Log with Chain Verification
- Human Review Queue & Golden Set Feedback Loop
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi import Response as FastAPIResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from audit_v2.analytics.aggregator import aggregate_results, compute_prediction_interval
from audit_v2.analytics.risk_predictor import predict_risk, severity_counts
from audit_v2.analytics.risk_scorer import (
    compute_document_score,
    risk_explanation_for,
    risk_level_for,
)
from audit_v2.domain.adjudicator import Adjudicator
from audit_v2.domain.catalog_loader import load_catalog
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
from audit_v2.extraction.classifier import classify_document_from_data
from audit_v2.extraction.preview import generate_preview
from audit_v2.orchestration.activities import extract_document
from audit_v2.orchestration.cluster_audit import ClusterAuditor
from audit_v2.orchestration.review_queue import ReviewAction, ReviewQueue
from audit_v2.persistence.audit_log import AuditLog
from audit_v2.persistence.permission_matrix import (
    Resource,
)
from audit_v2.persistence.provenance import ProvenanceGraph
from audit_v2.reporting.report_builders import generate_docx_report, generate_pdf_report

CATALOG = load_catalog()
CATALOG_BY_ID = {c.check_id: c for c in CATALOG.checks}

#: Synthetic check id for extraction disagreements — not a catalog check; it
#: represents "two extraction methods disagreed" and routes to human review.
DISAGREEMENT_CHECK_ID = "CHK-EXTRACT-DISAGREE-001"


def extraction_mode_of(doc: ExtractedDocument) -> str:
    """Classify how a document was extracted: dual | regex | vlm | vlm_text."""
    version = doc.extractor_version
    if version.startswith("dual"):
        return "dual"
    if version.startswith("vlm_text"):
        return "vlm_text"
    if version.startswith("vlm"):
        return "vlm"
    return "regex"


def _disagreement_finding(doc: ExtractedDocument, tenant_id: str) -> Finding | None:
    if not doc.extraction_disagreements:
        return None
    fields = ", ".join(sorted(doc.extraction_disagreements))
    return Finding(
        finding_id=f"fnd_dsg_{doc.document_id}",
        check_id=DISAGREEMENT_CHECK_ID,
        document_id=doc.document_id,
        tenant_id=tenant_id,
        status=FindingStatus.NEEDS_REVIEW,
        severity=Severity.MEDIUM,
        message=(
            f"Regex and VLM extraction disagreed on {len(doc.extraction_disagreements)} "
            f"field(s): {fields}"
        ),
        actual=fields,
        decision_fingerprint="deterministic:extractor-agreement",
        ruleset_version="ruleset_v2.0",
        requires_human_review=True,
    )


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


class ReportRequest(BaseModel):
    documents: list[dict[str, Any]]
    findings: list[dict[str, Any]] = Field(default_factory=list)
    audit_title: str = "Audit V2 Report"


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


def _failed_rule(f: Finding) -> dict[str, Any]:
    entry = CATALOG_BY_ID.get(f.check_id)
    return {
        "rule_id": f.check_id,
        "rule_title": entry.title if entry else f.check_id,
        "finding": f.message,
        "evidence": f.actual or "",
        "impact": entry.failure_message if entry else "",
        "recommendation": "Fix the stated value or provide supporting documentation.",
        "severity": f.severity.value,
        "page_number": f.evidence[0].page if f.evidence else None,
    }


def enrich_document(
    doc: ExtractedDocument,
    filename: str,
    findings: list[Finding],
    data: bytes,
    mime_type: str,
) -> dict[str, Any]:
    failed = [f for f in findings if f.document_id == doc.document_id]
    score = compute_document_score(failed)
    counts = severity_counts(failed)
    return {
        "document_id": doc.document_id,
        "document_name": filename,
        "document_type": doc.doc_type.value,
        "passed": score >= 80.0,
        "score": round(score, 2),
        "risk_level": risk_level_for(score, failed),
        "risk_explanation": risk_explanation_for(score, failed),
        "failed_rules": [_failed_rule(f) for f in failed],
        "ml_prediction": predict_risk(score, counts),
        "confidence_score": round(score, 2),
        "human_review_recommended": bool(doc.extraction_disagreements)
        or any(f.requires_human_review for f in failed),
        "remarks": doc.narrative_report or "",
        "preview_base64": generate_preview(data, mime_type),
        "page_count": doc.page_count,
        "summary_text": doc.narrative_report or "",
        "metadata": doc.header.model_dump(),
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
    pending_enrich: list[tuple[ExtractedDocument, str, bytes, str]] = []

    for file in files:
        data = await file.read()
        document_id = f"doc_{uuid.uuid4().hex[:8]}"
        mime_type = file.content_type or "application/pdf"

        detected_type, _ = classify_document_from_data(data, mime_type)
        res = extract_document(
            data=data,
            document_id=document_id,
            tenant_id=tenant_id,
            mime_type=mime_type,
            doc_type=detected_type,
        )

        if res.error or res.document is None:
            logger.warning("Failed to extract file %s: %s", file.filename, res.error)
            continue

        doc = res.document
        DOCUMENTS_STORE[doc.document_id] = doc
        ingested_docs.append(doc)
        pending_enrich.append((doc, file.filename, data, mime_type))
        extraction_results.append({
            "filename": file.filename,
            "document_id": doc.document_id,
            "doc_type": doc.doc_type.value,
            "is_vlm_fallback": extraction_mode_of(doc) != "regex",
            "extraction_mode": extraction_mode_of(doc),
            "extractor_version": doc.extractor_version,
            "pages": doc.page_count,
            "disagreement_count": len(doc.extraction_disagreements),
            "disagreement_fields": sorted(doc.extraction_disagreements),
            "has_narrative_report": doc.narrative_report is not None,
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
                "extraction_mode": extraction_mode_of(doc),
                "pages": doc.page_count,
                "disagreement_count": len(doc.extraction_disagreements),
            },
        )

        # Two-method extraction disagreement -> human review (PHASES_V2 §4
        # Phase 8: escalate rather than pick a winner silently).
        disagreement_finding = _disagreement_finding(doc, tenant_id)
        if disagreement_finding is not None:
            total_val = (
                float(doc.header.grand_total.decimal_value)
                if doc.header.grand_total
                else 0.0
            )
            REVIEW_QUEUE.enqueue(
                finding=disagreement_finding,
                document_id=doc.document_id,
                tenant_id=tenant_id,
                total_value=total_val,
            )
            AUDIT_LOG.log(
                entry_id=f"log_{uuid.uuid4().hex[:8]}",
                tenant_id=tenant_id,
                action="extraction_disagreement",
                resource_type=Resource.DOCUMENT,
                resource_id=doc.document_id,
                actor_id="system",
                payload={"disagreed_fields": sorted(doc.extraction_disagreements)},
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

    enriched = [
        enrich_document(doc, filename, batch_findings, data, mime_type)
        for doc, filename, data, mime_type in pending_enrich
    ]

    first_doc = ingested_docs[0].model_dump() if ingested_docs else None

    return {
        "message": f"Successfully ingested batch of {len(ingested_docs)} document(s)",
        "count": len(ingested_docs),
        "documents": [d.model_dump() for d in ingested_docs],
        "document": first_doc,
        "extraction_results": extraction_results,
        "findings": [f.model_dump() for f in batch_findings],
        "document_results": enriched,
        "prediction_interval": compute_prediction_interval(
            [e["score"] for e in enriched]
        ),
        "analytics": aggregate_results(enriched),
        "is_vlm_fallback": any(
            extraction_mode_of(d) != "regex" for d in ingested_docs
        ),
        "requires_human_review": any(
            d.extraction_disagreements for d in ingested_docs
        ),
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


@app.get("/api/v2/audit/eval")
def get_eval() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "evaluation" / "baselines" / "v2.json"
    if not path.exists():
        return {"metrics": None, "baselines": None}
    data = json.loads(path.read_text(encoding="utf-8"))
    cats = data.get("per_category", {})
    tp = sum(c.get("tp", 0) for c in cats.values())
    fp = sum(c.get("fp", 0) for c in cats.values())
    fn = sum(c.get("fn", 0) for c in cats.values())
    tn = sum(c.get("tn", 0) for c in cats.values())
    denom = tp + fp + fn + tn
    overall = data.get("overall", {})
    return {
        "metrics": {
            "accuracy": round((tp + tn) / denom, 4) if denom else None,
            "precision": overall.get("precision"),
            "recall": overall.get("recall"),
            "f1_score": overall.get("f1"),
            "false_positive_rate": round(fp / (fp + tn), 4) if (fp + tn) else None,
            "false_negative_rate": round(fn / (fn + tp), 4) if (fn + tp) else None,
            "average_latency_seconds": None,
            "average_confidence_score": None,
        },
        "baselines": data,
    }


@app.post("/api/v2/audit/report")
def generate_report(payload: ReportRequest, format: str = "docx") -> FastAPIResponse:
    if format == "docx":
        content = generate_docx_report(payload.model_dump())
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        suffix = "docx"
    elif format == "pdf":
        content = generate_pdf_report(payload.model_dump())
        media = "application/pdf"
        suffix = "pdf"
    else:
        raise HTTPException(status_code=400, detail="format must be 'docx' or 'pdf'")
    stamp = uuid.uuid4().hex[:8]
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="TrustAudit_Report_{stamp}.{suffix}"'},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
