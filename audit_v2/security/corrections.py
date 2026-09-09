"""Version-checked reviewer corrections with retained source and audit history."""
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from audit_v2.domain.evidence import EvidenceNature, PipelineEvidence
from audit_v2.domain.finding_generator import _document_hash
from audit_v2.domain.models import DocumentHeader, LineItem, ProvenancedValue
from audit_v2.pipeline.evidence_pipeline import DocumentPipelineResult
from audit_v2.pipeline.events import NullProgressSink
from audit_v2.security.auth import principal, require_reviewer

router = APIRouter(prefix="/api/v2/documents", tags=["corrections"])
HEADER_FIELDS = {
    "vendor_name", "vendor_gstin", "buyer_name", "buyer_gstin", "invoice_number",
    "po_number", "challan_number", "grn_number", "invoice_date", "due_date",
    "order_date", "delivery_date", "received_date", "grn_date", "po_reference",
    "subtotal", "grand_total", "discount_amount",
}
LINE_FIELDS = {
    "description", "quantity", "unit_price", "line_total", "quantity_unit",
    "hsn_sac", "item_code", "po_line_reference",
}


class Correction(BaseModel):
    path: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2000)
    page: int = Field(ge=1)
    source_quote: str = Field(min_length=1, max_length=4000)


class CorrectionRequest(BaseModel):
    expected_revision: str
    reason: str = Field(min_length=3, max_length=4000)
    changes: list[Correction] = Field(min_length=1, max_length=50)


@router.get("/{document_id}/revision")
def revision(document_id: str) -> dict:
    from audit_v2 import server

    tenant = principal().tenant_id
    with server._PROCESS_LOCK, server.OPERATIONAL_STORE.transaction(tenant) as tx:
        state = tx.load() or {}
        document = state.get("documents", {}).get(document_id)
        if document is None:
            raise HTTPException(404, "Document not found")
        from audit_v2.domain.models import ExtractedDocument

        parsed = ExtractedDocument.model_validate(document)
        return {
            "revision": _document_hash(parsed), "document": document,
            "corrections": [c for c in state.get("corrections", [])
                            if c["document_id"] == document_id],
        }


@router.post("/{document_id}/corrections")
def correct(document_id: str, payload: CorrectionRequest) -> dict:
    from audit_v2 import server

    actor = require_reviewer()
    with server._PROCESS_LOCK, server.OPERATIONAL_STORE.transaction(actor.tenant_id) as tx:
        before = tx.load() or {}
        server._restore(actor.tenant_id, before)
        original = server.DOCUMENTS_STORE.get(document_id)
        if original is None or original.tenant_id != actor.tenant_id:
            raise HTTPException(404, "Document not found")
        if payload.expected_revision != _document_hash(original):
            raise HTTPException(409, "Document changed; reload its revision before correcting")
        if len({c.path for c in payload.changes}) != len(payload.changes):
            raise HTTPException(422, "Each field may appear only once")
        corrected = original.model_copy(deep=True)
        changes = []
        for change in payload.changes:
            target: DocumentHeader | LineItem
            if change.page > original.page_count or not change.source_quote.strip():
                raise HTTPException(422, "Provide a source quote from an existing page")
            if not change.value.strip():
                raise HTTPException(422, "Correction value cannot be blank")
            header = re.fullmatch(r"header\.([a-z_]+)", change.path)
            line = re.fullmatch(r"line_items\[(\d+)\]\.([a-z_]+)", change.path)
            if header and header[1] in HEADER_FIELDS:
                target, field = corrected.header, header[1]
            elif line and line[2] in LINE_FIELDS and int(line[1]) < len(corrected.line_items):
                target, field = corrected.line_items[int(line[1])], line[2]
            else:
                raise HTTPException(422, "Unsupported correction field")
            previous = getattr(target, field)
            if field in {"subtotal", "grand_total", "discount_amount", "quantity", "unit_price", "line_total"}:
                try:
                    if not Decimal(change.value).is_finite():
                        raise ValueError("Non-finite amount")
                except (InvalidOperation, ValueError) as exc:
                    raise HTTPException(422, "Use a finite number without currency symbols") from exc
            replacement = ProvenancedValue(
                value=change.value.strip(), raw=change.source_quote, page=change.page,
                confidence=0.5, currency=previous.currency if previous else None,
                source_id=f"reviewer:{actor.actor_id}", label=change.path,
                text_span=change.source_quote,
            )
            setattr(target, field, replacement)
            changes.append({**change.model_dump(), "previous": previous.model_dump(mode="json")
                            if previous else None})
        correction_id = "cor_" + uuid.uuid4().hex
        entry = {
            "correction_id": correction_id, "document_id": document_id,
            "actor_id": actor.actor_id, "reason": payload.reason,
            "previous_revision": payload.expected_revision, "changes": changes,
            "created_at": datetime.now(UTC).isoformat(),
            "original_document": original.model_dump(mode="json"),
        }
        corrected.review_reasons.append(f"Reviewer correction {correction_id} requires review")
        evidence = list(server.EVIDENCE_STORE.get(document_id, []))
        evidence.append(PipelineEvidence(
            document_id=document_id, nature=EvidenceNature.EXTRACTED_FIELDS,
            source="reviewer_correction", derived_from=[e.evidence_id for e in evidence],
            payload=entry, summary=payload.reason, confidence=0.5,
        ))
        pipeline = DocumentPipelineResult(
            document_id=document_id, doc_type=corrected.doc_type, document=corrected,
            evidences=evidence, requires_human_review=True,
            contradictions=server.CONTRADICTION_STORE.get(document_id, []),
        )
        old_result = server.RESULTS_STORE.get(document_id, {})
        try:
            result = server._process_documents_impl(
                [(old_result.get("document_name", document_id), b"", "application/pdf", pipeline)],
                actor.tenant_id, NullProgressSink(),
            )
            server.RESULTS_STORE[document_id]["preview_base64"] = old_result.get("preview_base64", "")
            for item in server.REVIEW_QUEUE._items.values():
                if item.document_id == document_id and item.status in {"PENDING", "ESCALATED"}:
                    item.evidence_corrected_by = actor.actor_id
            entry["revision"] = _document_hash(corrected)
            snapshot = server._snapshot(actor.tenant_id)
            snapshot["corrections"] = [*before.get("corrections", []), entry]
            tx.save(snapshot, "reviewer_correction_committed")
        except Exception:
            server._restore(actor.tenant_id, before)
            raise
        return {**server._present_batch(result), "revision": entry["revision"],
                "correction_id": correction_id}
