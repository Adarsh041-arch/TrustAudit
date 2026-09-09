"""Per-doctype structured-extraction schemas (new_requirements.md §2).

Each document type has a fixed extraction schema — a Pydantic model whose
``.model_json_schema()`` drives guided decoding through the local GLM-OCR gateway
and whose ``.model_validate()`` validates the model's JSON reply. Every schema
carries the doctype's necessary fields **plus** ``other_necessary_details`` — a
free list the model uses for anything salient the fixed fields don't capture.

``to_extracted_document`` maps any of these structured results onto the single
canonical :class:`~audit_v2.domain.models.ExtractedDocument` so that all the
existing deterministic validators keep running unchanged.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from audit_v2.domain.models import (
    CertificateGoodsItem,
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
    LineItem,
    ProvenancedValue,
    TaxLine,
)
from audit_v2.extraction.parser import normalize_locale

# ─── Reusable sub-schemas ─────────────────────────────────────────────────────


class LineItemSchema(BaseModel):
    description: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    line_total: str | None = None
    hsn_sac: str | None = None
    quantity_unit: str | None = None


class TaxLineSchema(BaseModel):
    description: str | None = None
    taxable_value: str | None = None
    rate: str | None = None
    cgst: str | None = None
    sgst: str | None = None
    total_tax: str | None = None


# ─── Per-doctype schemas (math-heavy: invoice / PO / DC / GRN) ─────────────────


class InvoiceExtraction(BaseModel):
    currency: str | None = None
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    buyer_name: str | None = None
    buyer_gstin: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    po_reference: str | None = None
    subtotal: str | None = None
    discount_amount: str | None = None
    grand_total: str | None = None
    amount_in_words: str | None = None
    bank_account_number: str | None = None
    bank_ifsc: str | None = None
    line_items: list[LineItemSchema] = Field(default_factory=list)
    tax_lines: list[TaxLineSchema] = Field(default_factory=list)
    other_necessary_details: list[str] = Field(default_factory=list)


class PurchaseOrderExtraction(BaseModel):
    currency: str | None = None
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    buyer_name: str | None = None
    po_number: str | None = None
    order_date: str | None = None
    delivery_date: str | None = None
    subtotal: str | None = None
    grand_total: str | None = None
    line_items: list[LineItemSchema] = Field(default_factory=list)
    other_necessary_details: list[str] = Field(default_factory=list)


class DeliveryChallanExtraction(BaseModel):
    vendor_name: str | None = None
    buyer_name: str | None = None
    challan_number: str | None = None
    delivery_date: str | None = None
    vehicle_number: str | None = None
    po_reference: str | None = None
    line_items: list[LineItemSchema] = Field(default_factory=list)
    other_necessary_details: list[str] = Field(default_factory=list)


class GoodsReceiptExtraction(BaseModel):
    vendor_name: str | None = None
    buyer_name: str | None = None
    grn_number: str | None = None
    grn_date: str | None = None
    received_date: str | None = None
    po_reference: str | None = None
    line_items: list[LineItemSchema] = Field(default_factory=list)
    other_necessary_details: list[str] = Field(default_factory=list)


# ─── Per-doctype schemas (free-text: contract / letter) ───────────────────────


class ContractExtraction(BaseModel):
    party_a: str | None = None
    party_b: str | None = None
    effective_date: str | None = None
    expiry_date: str | None = None
    reference: str | None = None
    value_amount: str | None = None
    subject: str | None = None
    narrative_report: str | None = None
    other_necessary_details: list[str] = Field(default_factory=list)


class LetterExtraction(BaseModel):
    sender: str | None = None
    recipient: str | None = None
    date: str | None = None
    reference: str | None = None
    subject: str | None = None
    narrative_report: str | None = None
    other_necessary_details: list[str] = Field(default_factory=list)


class CertificateGoodsSchema(BaseModel):
    description: str | None = None
    hs_code: str | None = None
    quantity: str | None = None
    quantity_unit: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None


class CertificateOfOriginExtraction(BaseModel):
    certificate_number: str | None = None
    certificate_date: str | None = None
    exporter_name: str | None = None
    exporter_address: str | None = None
    consignee_name: str | None = None
    consignee_address: str | None = None
    country_of_origin: str | None = None
    issuing_authority: str | None = None
    signature_present: bool | None = None
    seal_present: bool | None = None
    goods: list[CertificateGoodsSchema] = Field(default_factory=list)
    other_necessary_details: list[str] = Field(default_factory=list)


class UnknownDocumentExtraction(BaseModel):
    detected_title: str | None = None
    narrative_report: str | None = None
    other_necessary_details: list[str] = Field(default_factory=list)


EXTRACTION_SCHEMA_BY_TYPE: dict[DocumentType, type[BaseModel]] = {
    DocumentType.INVOICE: InvoiceExtraction,
    DocumentType.PURCHASE_ORDER: PurchaseOrderExtraction,
    DocumentType.DELIVERY_CHALLAN: DeliveryChallanExtraction,
    DocumentType.GOODS_RECEIPT_NOTE: GoodsReceiptExtraction,
    DocumentType.CONTRACT: ContractExtraction,
    DocumentType.LETTER: LetterExtraction,
    DocumentType.CERTIFICATE_OF_ORIGIN: CertificateOfOriginExtraction,
    DocumentType.UNKNOWN: UnknownDocumentExtraction,
}


def supplement_from_transcript(
    instance: BaseModel,
    doc_type: DocumentType,
    transcript: str,
) -> BaseModel:
    """Fill only missing, explicitly labelled fields from the raw transcription."""
    if doc_type != DocumentType.CERTIFICATE_OF_ORIGIN:
        return instance

    data = instance.model_dump(mode="python")
    patterns = {
        "certificate_number": r"(?im)^\s*Certificate\s+No\.?\s*:\s*([^\r\n]+)",
        "certificate_date": r"(?im)^\s*Date\s*:\s*([^\r\n]+)",
        "exporter_name": r"(?im)^\s*Exporter\s*:\s*([^\r\n]+)",
        "consignee_name": r"(?im)^\s*Consignee\s*:\s*([^\r\n]+)",
        "country_of_origin": r"(?i)\boriginate(?:d|s)?\s+in\s+([A-Za-z ]+?)[.\r\n]",
    }
    for field_name, pattern in patterns.items():
        if data.get(field_name):
            continue
        match = re.search(pattern, transcript)
        if match:
            data[field_name] = match.group(1).strip().rstrip(",")

    goods = data.get("goods") or []
    if goods:
        first = goods[0]
        labelled_goods = {
            "invoice_number": r"(?im)^\s*Invoice\s+No\.?\s*\n?\s*([^\r\n]+)",
            "invoice_date": r"(?im)^\s*Invoice\s+Date\s*\n?\s*([^\r\n]+)",
        }
        for field_name, pattern in labelled_goods.items():
            if first.get(field_name):
                continue
            match = re.search(pattern, transcript)
            if match:
                first[field_name] = match.group(1).strip()

    return type(instance).model_validate(data)


# ─── Mapping onto the canonical ExtractedDocument ─────────────────────────────

#: Free-text schemas use natural field names; alias them onto DocumentHeader.
_ALIASES: dict[DocumentType, dict[str, str]] = {
    DocumentType.CONTRACT: {
        "vendor_name": "party_a",
        "buyer_name": "party_b",
        "invoice_date": "effective_date",
        "expiry_date": "expiry_date",
        "po_reference": "reference",
        "grand_total": "value_amount",
    },
    DocumentType.LETTER: {
        "vendor_name": "sender",
        "buyer_name": "recipient",
        "invoice_date": "date",
        "po_reference": "reference",
    },
    DocumentType.CERTIFICATE_OF_ORIGIN: {
        "vendor_name": "exporter_name",
        "buyer_name": "consignee_name",
        "invoice_date": "certificate_date",
    },
}

#: DocumentHeader ProvenancedValue fields the mapper will populate when the
#: schema (directly or via an alias) carries the corresponding value.
_HEADER_FIELDS = (
    "vendor_name",
    "vendor_gstin",
    "buyer_name",
    "buyer_gstin",
    "invoice_number",
    "po_number",
    "challan_number",
    "grn_number",
    "invoice_date",
    "due_date",
    "po_reference",
    "order_date",
    "delivery_date",
    "grn_date",
    "received_date",
    "expiry_date",
    "subtotal",
    "discount_amount",
    "grand_total",
    "amount_in_words",
    "certificate_number",
    "certificate_date",
    "exporter_name",
    "exporter_address",
    "consignee_name",
    "consignee_address",
    "country_of_origin",
    "referenced_invoice_number",
    "referenced_invoice_date",
    "issuing_authority",
)


def _pv(
    val: Any,
    page: int = 1,
    confidence: float = 0.85,
    currency: str | None = None,
) -> ProvenancedValue | None:
    if val is None or str(val).strip() == "":
        return None
    s_val = str(val).strip()
    return ProvenancedValue(
        value=normalize_locale(s_val, None),
        raw=s_val,
        page=page,
        bbox=None,
        confidence=confidence,
        currency=currency,
    )


def _schema_attr(instance: BaseModel, header_field: str, doc_type: DocumentType) -> Any:
    """Read the value for a header field, following any per-type alias."""
    alias = _ALIASES.get(doc_type, {}).get(header_field, header_field)
    return getattr(instance, alias, None)


def _line_items(instance: BaseModel, currency: str | None = None) -> list[LineItem]:
    items: list[LineItem] = []
    for idx, raw in enumerate(getattr(instance, "line_items", []) or [], start=1):
        desc = _pv(raw.description)
        qty = _pv(raw.quantity)
        price = _pv(raw.unit_price, currency=currency)
        total = _pv(raw.line_total, currency=currency)
        if desc and qty and price and total:
            items.append(
                LineItem(
                    line_number=idx,
                    description=desc,
                    quantity=qty,
                    unit_price=price,
                    line_total=total,
                    hsn_sac=_pv(raw.hsn_sac),
                    quantity_unit=_pv(raw.quantity_unit),
                )
            )
    return items


def _tax_lines(instance: BaseModel, currency: str | None = None) -> list[TaxLine]:
    lines: list[TaxLine] = []
    for idx, raw in enumerate(getattr(instance, "tax_lines", []) or [], start=1):
        desc = _pv(raw.description)
        taxable = _pv(raw.taxable_value, currency=currency)
        rate = _pv(raw.rate)
        cgst = _pv(raw.cgst, currency=currency)
        sgst = _pv(raw.sgst, currency=currency)
        total_tax = _pv(raw.total_tax, currency=currency)
        if desc and taxable and rate and cgst and sgst and total_tax:
            lines.append(
                TaxLine(
                    line_number=idx,
                    description=desc,
                    taxable_value=taxable,
                    rate=rate,
                    cgst=cgst,
                    sgst=sgst,
                    total_tax=total_tax,
                )
            )
    return lines


def _certificate_goods(instance: BaseModel) -> list[CertificateGoodsItem]:
    items: list[CertificateGoodsItem] = []
    for idx, raw in enumerate(getattr(instance, "goods", []) or [], start=1):
        description = _pv(raw.description)
        hs_code = _pv(raw.hs_code)
        quantity = _pv(raw.quantity)
        if not description or not hs_code or not quantity:
            continue
        items.append(
            CertificateGoodsItem(
                line_number=idx,
                description=description,
                hs_code=hs_code,
                quantity=quantity,
                quantity_unit=_pv(raw.quantity_unit),
                invoice_number=_pv(raw.invoice_number),
                invoice_date=_pv(raw.invoice_date),
            )
        )
    return items


def to_extracted_document(
    instance: BaseModel,
    *,
    document_id: str,
    tenant_id: str,
    doc_type: DocumentType,
    page_count: int,
    extractor_version: str = "pipeline_vlm_1.0.0",
) -> ExtractedDocument:
    """Map a structured extraction result onto the canonical ExtractedDocument."""
    currency = getattr(instance, "currency", None)
    monetary_fields = {"subtotal", "discount_amount", "grand_total"}
    header_kwargs: dict[str, ProvenancedValue] = {}
    for field_name in _HEADER_FIELDS:
        pv = _pv(
            _schema_attr(instance, field_name, doc_type),
            currency=currency if field_name in monetary_fields else None,
        )
        if pv is not None:
            header_kwargs[field_name] = pv

    bank_details: dict[str, str] = {}
    acct = getattr(instance, "bank_account_number", None)
    ifsc = getattr(instance, "bank_ifsc", None)
    if acct:
        bank_details["account_number"] = str(acct).strip()
    if ifsc:
        bank_details["ifsc"] = str(ifsc).strip()

    header = DocumentHeader.model_validate(
        dict(
            document_id=document_id,
            doc_type=doc_type,
            bank_details=bank_details or None,
            **header_kwargs,
        )
    )
    if doc_type == DocumentType.CERTIFICATE_OF_ORIGIN:
        header.signature_present = getattr(instance, "signature_present", None)
        header.seal_present = getattr(instance, "seal_present", None)
        goods = getattr(instance, "goods", []) or []
        if goods:
            header.referenced_invoice_number = _pv(goods[0].invoice_number)
            header.referenced_invoice_date = _pv(goods[0].invoice_date)

    coverage = Coverage(
        pages_total=page_count,
        pages_examined=page_count,
        coverage_complete=True,
    )
    return ExtractedDocument(
        document_id=document_id,
        tenant_id=tenant_id,
        doc_type=doc_type,
        header=header,
        line_items=_line_items(instance, currency),
        tax_lines=_tax_lines(instance, currency),
        certificate_goods=_certificate_goods(instance),
        coverage=coverage,
        page_count=page_count,
        extractor_version=extractor_version,
        narrative_report=getattr(instance, "narrative_report", None),
    )
