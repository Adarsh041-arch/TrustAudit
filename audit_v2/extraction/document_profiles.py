"""Central document-type registry for classification, extraction, and audit routing."""
from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel

from audit_v2.domain.models import DocumentType
from audit_v2.extraction.schemas import EXTRACTION_SCHEMA_BY_TYPE


@dataclass(frozen=True)
class Signature:
    pattern: re.Pattern[str]
    weight: float
    title: bool = False


@dataclass(frozen=True)
class DocumentProfile:
    doc_type: DocumentType
    display_name: str
    schema_model: type[BaseModel]
    signatures: tuple[Signature, ...]
    required_fields: tuple[str, ...]
    auditable: bool = True


def _sig(pattern: str, weight: float, *, title: bool = False) -> Signature:
    return Signature(re.compile(pattern, re.IGNORECASE), weight, title)


DOCUMENT_PROFILES: dict[DocumentType, DocumentProfile] = {
    DocumentType.CERTIFICATE_OF_ORIGIN: DocumentProfile(
        DocumentType.CERTIFICATE_OF_ORIGIN,
        "Certificate of Origin",
        EXTRACTION_SCHEMA_BY_TYPE[DocumentType.CERTIFICATE_OF_ORIGIN],
        (
            _sig(
                r"(?m)^\s*\|?\s*(?P<evidence>CERTIFICATE\s+OF\s+ORIGIN)"
                r"(?=\s*(?:\([^)]*\))?\s*\|?\s*$).*?$",
                1.0,
                title=True,
            ),
            _sig(r"\bCertificate\s+No\.?\b", 0.25),
            _sig(r"\bExporter\b", 0.15),
            _sig(r"\bConsignee\b", 0.15),
            _sig(r"\bHS\s*Code\b", 0.1),
        ),
        ("certificate_number", "certificate_date", "exporter_name", "consignee_name"),
    ),
    DocumentType.INVOICE: DocumentProfile(
        DocumentType.INVOICE,
        "Invoice",
        EXTRACTION_SCHEMA_BY_TYPE[DocumentType.INVOICE],
        (
            _sig(r"(?m)^\s*\|?\s*Tax\s*Invoice\s*\|?\s*$", 1.0, title=True),
            _sig(r"(?m)^\s*\|?\s*Commercial\s*Invoice\s*\|?\s*$", 1.0, title=True),
            _sig(r"(?m)^\s*\|?\s*Invoice\s*\|?\s*$", 0.9, title=True),
            _sig(r"\bInvoice\b", 0.15),
            _sig(r"\bInvoice\s*(?:No|Number|#)\b", 0.25),
        ),
        ("vendor_name", "invoice_date", "grand_total"),
    ),
    DocumentType.PURCHASE_ORDER: DocumentProfile(
        DocumentType.PURCHASE_ORDER,
        "Purchase Order",
        EXTRACTION_SCHEMA_BY_TYPE[DocumentType.PURCHASE_ORDER],
        (
            _sig(r"(?m)^\s*\|?\s*Purchase\s*Order\s*\|?\s*$", 1.0, title=True),
            _sig(r"\bPurchase\s*Order\b", 0.15),
            _sig(r"\bPO\s*(?:No|Number|#)\b", 0.25),
        ),
        ("vendor_name", "order_date"),
    ),
    DocumentType.DELIVERY_CHALLAN: DocumentProfile(
        DocumentType.DELIVERY_CHALLAN,
        "Delivery Challan",
        EXTRACTION_SCHEMA_BY_TYPE[DocumentType.DELIVERY_CHALLAN],
        (
            _sig(r"(?m)^\s*\|?\s*Delivery\s+Challan\s*\|?\s*$", 1.0, title=True),
            _sig(r"\bDC\s*(?:No|Number|#)\b", 0.25),
            _sig(r"\bVehicle\s*(?:No|Number|#)\b", 0.15),
        ),
        ("vendor_name", "delivery_date"),
    ),
    DocumentType.GOODS_RECEIPT_NOTE: DocumentProfile(
        DocumentType.GOODS_RECEIPT_NOTE,
        "Goods Receipt Note",
        EXTRACTION_SCHEMA_BY_TYPE[DocumentType.GOODS_RECEIPT_NOTE],
        (
            _sig(r"(?m)^\s*\|?\s*Goods\s*(?:Receipt|Received)\s*Note\s*\|?\s*$", 1.0, title=True),
            _sig(r"\bGRN\s*(?:No|Number|#)\b", 0.25),
            _sig(r"\b(?:Material|Goods)\s*Received\b", 0.2),
        ),
        ("vendor_name", "grn_date"),
    ),
    DocumentType.CONTRACT: DocumentProfile(
        DocumentType.CONTRACT,
        "Contract",
        EXTRACTION_SCHEMA_BY_TYPE[DocumentType.CONTRACT],
        (
            _sig(r"(?m)^\s*\|?\s*(?:International\s+)?Sales\s*Contract\s*\|?\s*$", 1.0, title=True),
            _sig(r"(?m)^\s*\|?\s*(?:Proforma|Performa)\s*Invoice\s*\|?\s*$", 0.9, title=True),
            _sig(r"\bAgreement\b", 0.6),
            _sig(r"\bContract\b", 0.6),
            _sig(r"\bNon-?\s*Disclosure\b", 0.6),
            _sig(r"\bTerms\s+and\s+Conditions\b", 0.4),
        ),
        ("vendor_name", "buyer_name", "invoice_date"),
    ),
    DocumentType.LETTER: DocumentProfile(
        DocumentType.LETTER,
        "Letter",
        EXTRACTION_SCHEMA_BY_TYPE[DocumentType.LETTER],
        (
            _sig(r"\bLetter\b", 0.7, title=True),
            _sig(r"\bMemo(?:randum)?\b", 0.7, title=True),
            _sig(r"\bNotice\b", 0.7, title=True),
            _sig(r"\bCorrespondence\b", 0.5),
        ),
        ("vendor_name", "invoice_date"),
    ),
    DocumentType.UNKNOWN: DocumentProfile(
        DocumentType.UNKNOWN,
        "Unsupported document",
        EXTRACTION_SCHEMA_BY_TYPE[DocumentType.UNKNOWN],
        (),
        (),
        auditable=False,
    ),
}


def profile_for(doc_type: DocumentType) -> DocumentProfile:
    return DOCUMENT_PROFILES[doc_type]
