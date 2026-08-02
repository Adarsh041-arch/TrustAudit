from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from audit_v2.domain.models import DocumentStatus, DocumentType, ExtractedDocument
from audit_v2.extraction.classifier import EXTRACTOR_REGISTRY
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
    extractor_cls = EXTRACTOR_REGISTRY.get(doc_type)
    if extractor_cls is None:
        return ExtractionResult(error=f"No extractor registered for {doc_type}")
    ext = extractor_cls()
    try:
        doc = ext.extract(data, mime_type)
        doc.document_id = document_id
        doc.tenant_id = tenant_id
        return ExtractionResult(document=doc, text=_raw_text(data, mime_type))
    except ValueError as e:
        vlm_res = _try_vlm_fallback(data, mime_type, document_id, tenant_id)
        if vlm_res is not None:
            return vlm_res
        return ExtractionResult(error=str(e))


def _try_vlm_fallback(
    data: bytes, mime_type: str, document_id: str, tenant_id: str,
) -> ExtractionResult | None:
    if not os.getenv("NVIDIA_API_KEY"):
        return None
    try:
        from audit_v2.extraction.vlm_extractor import VlmExtractor
        vlm = VlmExtractor()
        doc = vlm.extract(data, mime_type)
        doc.document_id = document_id
        doc.tenant_id = tenant_id
        return ExtractionResult(document=doc, text=_raw_text(data, mime_type))
    except Exception as exc:
        logger.warning("VLM fallback extraction failed for %s: %s", document_id, exc)
        return None



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
    return document
