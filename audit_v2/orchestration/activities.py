from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from audit_v2.domain.models import (
    TEXT_DOC_TYPES,
    DocumentStatus,
    DocumentType,
    ExtractedDocument,
    ProvenancedValue,
)
from audit_v2.extraction.classifier import (
    EXTRACTOR_REGISTRY,
    classify_document_detailed,
    classify_document_from_data_detailed,
)
from audit_v2.extraction.merge import merge_extractions
from audit_v2.extraction.text_extractor import TextExtractor
from audit_v2.ingestion.document_store import DocumentRecord, DocumentStore
from audit_v2.ingestion.pdf_utils import (
    count_pdf_pages,
    has_text_layer,
    is_encrypted_pdf,
    is_supported_mime,
    is_valid_file_size,
    is_valid_page_count,
    is_zero_byte,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    valid: bool
    error: str | None = None
    quarantine_type: str | None = None


def validate_document(
    data: bytes,
    mime_type: str,
    file_size: int,
) -> ValidationResult:
    if is_zero_byte(file_size):
        return ValidationResult(valid=False, error="Zero-byte file", quarantine_type="QUARANTINED")
    if not is_supported_mime(mime_type):
        msg = f"Unsupported MIME type: {mime_type}"
        return ValidationResult(valid=False, error=msg, quarantine_type="QUARANTINED")
    if not is_valid_file_size(file_size):
        return ValidationResult(
            valid=False, error="File exceeds 100 MB limit", quarantine_type="QUARANTINED"
        )
    if mime_type == "application/pdf" and is_encrypted_pdf(data):
        return ValidationResult(
            valid=False, error="PDF is encrypted/password-protected",
            quarantine_type="QUARANTINED_ENCRYPTED",
        )
    return ValidationResult(valid=True)


def check_dedup(
    store: DocumentStore,
    tenant_id: str,
    content_hash: str,
) -> DocumentRecord | None:
    return store.get_by_hash(tenant_id, content_hash)


def process_pdf_pages(data: bytes) -> dict:
    page_count = count_pdf_pages(data)
    if page_count is None:
        return {"page_count": 0, "has_text_layer": False, "error": "Cannot parse PDF"}
    if not is_valid_page_count(page_count):
        return {
            "page_count": page_count, "has_text_layer": False,
            "error": f"Page count {page_count} exceeds limit of 500",
        }
    text_layer = has_text_layer(data)
    return {"page_count": page_count, "has_text_layer": text_layer, "error": None}


def transition_document(
    store: DocumentStore,
    document_id: str,
    from_status: DocumentStatus,
    to_status: DocumentStatus,
) -> None:
    doc = store.get(document_id)
    if doc is None:
        raise ValueError(f"Document {document_id} not found")
    if doc.status != from_status.value:
        raise ValueError(
            f"Cannot transition from {doc.status} to {to_status.value}: "
            f"document is in state {doc.status}"
        )
    store.update_status(document_id, to_status.value)


@dataclass
class ExtractionResult:
    document: ExtractedDocument | None = None
    error: str | None = None
    text: str = ""


def extract_document(
    data: bytes,
    mime_type: str,
    document_id: str,
    tenant_id: str,
    doc_type: DocumentType = DocumentType.INVOICE,
) -> ExtractionResult:
    """Extract a document, branching on its type.

    - Text documents (contract/letter): VLM-only — key fields + narrative
      report. No regex pass; there are no tables to regex.
    - Tabular documents (invoice/PO/DC/GRN): two parallel extraction passes
      (regex + VLM) merged field-by-field; disagreements are recorded on the
      merged document for human review.
    """
    if doc_type in TEXT_DOC_TYPES:
        return extract_text_with_vlm(data, mime_type, document_id, tenant_id, doc_type)
    return _extract_dual(data, mime_type, document_id, tenant_id, doc_type)


def _extract_dual(
    data: bytes,
    mime_type: str,
    document_id: str,
    tenant_id: str,
    doc_type: DocumentType,
) -> ExtractionResult:
    """Run the regex extractor and the VLM extractor in parallel, then merge."""
    raw_text = _raw_text(data, mime_type)

    with ThreadPoolExecutor(max_workers=2) as pool:
        regex_future = pool.submit(
            extract_with_regex, data, mime_type, document_id, tenant_id, doc_type,
        )
        vlm_future = pool.submit(
            extract_with_vlm, data, mime_type, document_id, tenant_id,
        )
        regex_res = regex_future.result()
        vlm_res = vlm_future.result()

    if regex_res.document is None and vlm_res.document is None:
        return ExtractionResult(
            error=regex_res.error or vlm_res.error or "Extraction returned None",
            text=raw_text,
        )
    if regex_res.document is None:
        return ExtractionResult(document=vlm_res.document, text=raw_text)
    if vlm_res.document is None:
        return ExtractionResult(document=regex_res.document, text=raw_text)

    merged = merge_extractions(regex_res.document, vlm_res.document).merged
    if merged.extraction_disagreements:
        logger.info(
            "Dual extraction for %s: %d disagreed fields → human review",
            document_id, len(merged.extraction_disagreements),
        )
    return ExtractionResult(document=merged, text=raw_text)


def extract_with_regex(
    data: bytes,
    mime_type: str,
    document_id: str,
    tenant_id: str,
    doc_type: DocumentType,
) -> ExtractionResult:
    """Regex-only extraction — the deterministic half of the dual pass."""
    extractor_cls = EXTRACTOR_REGISTRY.get(doc_type)
    if extractor_cls is None:
        return ExtractionResult(error=f"No extractor registered for {doc_type}")
    try:
        doc = extractor_cls().extract(data, mime_type)
        doc.document_id = document_id
        doc.tenant_id = tenant_id
        return ExtractionResult(document=doc, text=_raw_text(data, mime_type))
    except ValueError as e:
        logger.warning("Regex extraction failed for %s: %s", document_id, e)
        return ExtractionResult(error=str(e))


def extract_with_vlm(
    data: bytes,
    mime_type: str,
    document_id: str,
    tenant_id: str,
) -> ExtractionResult:
    """Grounded local vision extraction — the model half of the dual pass."""
    if os.getenv("V2_VISION_BACKEND", "qwen_ollama") == "none":
        return ExtractionResult(error="Local vision extraction is disabled")
    try:
        from audit_v2.extraction.vlm_extractor import render_pages_to_jpeg
        from audit_v2.gateway.vision_factory import create_vision_gateway
        from audit_v2.pipeline.evidence_pipeline import _run_glm_pages

        images = render_pages_to_jpeg(data, mime_type)
        if not images:
            return ExtractionResult(error="No document pages could be rendered")
        gateway = create_vision_gateway()
        if gateway is None:
            return ExtractionResult(error="Local vision extraction is disabled")
        decision = classify_document_from_data_detailed(data, mime_type)
        transcripts: dict[int, str] = {}
        if decision.doc_type == DocumentType.UNKNOWN:
            response = gateway.extract(
                images=[images[0]], prompt="Text Recognition:", tenant_id=tenant_id,
            )
            transcripts[1] = response.content.strip()
            decision = classify_document_detailed(
                transcripts[1],
                method=f"{getattr(gateway, 'backend', 'local_vision')}_transcription",
                page=1,
            )
        doc_type = decision.doc_type
        doc, _ = _run_glm_pages(
            images=images,
            document_id=document_id,
            tenant_id=tenant_id,
            doc_type=doc_type,
            gateway=gateway,
            evidences=[],
            transcripts=transcripts,
        )
        doc.classification_status = decision.status
        doc.classification_confidence = decision.confidence
        doc.classification_method = decision.method
        doc.classification_evidence = decision.evidence
        doc.alternative_types = decision.alternative_types
        return ExtractionResult(document=doc, text=_raw_text(data, mime_type))
    except Exception as exc:
        logger.warning("GLM-OCR extraction failed for %s: %s", document_id, exc)
        return ExtractionResult(error=str(exc))


def extract_text_with_vlm(
    data: bytes,
    mime_type: str,
    document_id: str,
    tenant_id: str,
    doc_type: DocumentType,
) -> ExtractionResult:
    """Grounded GLM-OCR extraction for free-text documents."""
    try:
        result = extract_with_vlm(data, mime_type, document_id, tenant_id)
        if result.document is not None and doc_type != DocumentType.UNKNOWN:
            result.document.doc_type = doc_type
            result.document.header.doc_type = doc_type
        return result
    except Exception as exc:
        logger.warning("GLM-OCR text extraction failed for %s: %s", document_id, exc)
        return ExtractionResult(error=str(exc))


def _raw_text(data: bytes, mime_type: str) -> str:
    """Raw document text, retained so §5 can scan what the model would see."""
    if mime_type == "text/plain":
        return data.decode("utf-8", errors="replace")
    if mime_type != "application/pdf":
        return ""
    try:
        return "\n".join(TextExtractor().extract_page_texts(data).values())
    except RuntimeError:
        logger.warning("Could not retrieve raw text for injection scan")
        return ""


def normalize_document(document: ExtractedDocument) -> ExtractedDocument:
    if document.header.received_date is None:
        from datetime import date
        document.header.received_date = ProvenancedValue(
            value=date.today().isoformat(),
            raw=date.today().isoformat(),
            confidence=1.0
        )
    return document
