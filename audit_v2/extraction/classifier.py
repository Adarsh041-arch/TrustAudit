from __future__ import annotations

import re

from audit_v2.domain.models import DocumentType
from audit_v2.extraction.base import BaseExtractor

EXTRACTOR_REGISTRY: dict[DocumentType, type[BaseExtractor]] = {}


def lazy_register() -> None:
    from audit_v2.extraction.invoice_extractor import InvoiceExtractor
    EXTRACTOR_REGISTRY[DocumentType.INVOICE] = InvoiceExtractor
    from audit_v2.extraction.po_extractor import POExtractor
    EXTRACTOR_REGISTRY[DocumentType.PURCHASE_ORDER] = POExtractor
    from audit_v2.extraction.delivery_challan_extractor import DeliveryChallanExtractor
    EXTRACTOR_REGISTRY[DocumentType.DELIVERY_CHALLAN] = DeliveryChallanExtractor
    from audit_v2.extraction.grn_extractor import GRNExtractor
    EXTRACTOR_REGISTRY[DocumentType.GOODS_RECEIPT_NOTE] = GRNExtractor


lazy_register()

_TYPE_SIGNATURES: list[tuple[DocumentType, list[re.Pattern], float]] = [
    (DocumentType.INVOICE, [
        re.compile(r"Tax\s*Invoice", re.IGNORECASE),
        re.compile(r"Invoice\s*(?:No|Number|#)", re.IGNORECASE),
    ], 0.4),
    (DocumentType.PURCHASE_ORDER, [
        re.compile(r"Purchase\s*Order", re.IGNORECASE),
        re.compile(r"PO\s*(?:No|Number|#)", re.IGNORECASE),
    ], 0.4),
    (DocumentType.DELIVERY_CHALLAN, [
        re.compile(r"Delivery\s+Challan", re.IGNORECASE),
        re.compile(r"DC\s*(?:No|Number|#)", re.IGNORECASE),
        re.compile(r"Vehicle\s*(?:No|Number|#)", re.IGNORECASE),
    ], 0.3),
    (DocumentType.GOODS_RECEIPT_NOTE, [
        re.compile(r"Goods\s*(?:Receipt|Received)\s*Note", re.IGNORECASE),
        re.compile(r"GRN\s*(?:No|Number|#)", re.IGNORECASE),
        re.compile(r"(?:Material|Goods)\s*Received", re.IGNORECASE),
    ], 0.3),
]


def classify_document(text: str) -> tuple[DocumentType, float]:
    best_type = DocumentType.INVOICE
    best_score = 0.0

    for doc_type, patterns, weight in _TYPE_SIGNATURES:
        score = 0.0
        for pat in patterns:
            if pat.search(text):
                score += weight
        if score > best_score:
            best_score = score
            best_type = doc_type

    return best_type, min(best_score, 1.0)


def classify_document_from_data(data: bytes, mime_type: str) -> tuple[DocumentType, float]:
    text = data.decode("utf-8", errors="replace") if mime_type == "text/plain" else ""
    if not text and mime_type == "application/pdf":
        from audit_v2.extraction.text_extractor import TextExtractor
        pages = TextExtractor().extract_page_texts(data)
        text = "\n".join(pages.values())
    return classify_document(text)
