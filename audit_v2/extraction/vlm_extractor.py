"""VLM-based document extractor — Phase 4 completion & Phase 5.1 (PHASES_V2 §4).

Uses NvidiaGateway to extract structured fields from scanned PDFs or image documents
where PyMuPDF text layer extraction fails or yields low confidence.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import fitz  # PyMuPDF

from audit_v2.domain.models import (
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
    LineItem,
    ProvenancedValue,
    TaxLine,
)
from audit_v2.extraction.base import BaseExtractor
from audit_v2.extraction.parser import normalize_locale
from audit_v2.gateway.nvidia_gateway import NvidiaGateway

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a high-precision document extraction engine.
Analyze the provided document page image(s) and extract all header fields,
line items, and tax lines.

Return ONLY a single valid JSON object with the following exact structure:
{
  "header": {
    "doc_type": "invoice|purchase_order|delivery_challan|goods_receipt_note",
    "vendor_name": "string or null",
    "vendor_address": "string or null",
    "vendor_gstin": "string or null",
    "buyer_name": "string or null",
    "buyer_gstin": "string or null",
    "invoice_date": "YYYY-MM-DD or string or null",
    "due_date": "YYYY-MM-DD or string or null",
    "po_reference": "string or null",
    "subtotal": "number as string or null",
    "grand_total": "number as string or null",
    "amount_in_words": "string or null",
    "bank_details": {"account_number": "...", "ifsc": "..."} or null,
    "order_date": "YYYY-MM-DD or null",
    "delivery_date": "YYYY-MM-DD or null",
    "grn_date": "YYYY-MM-DD or null"
  },
  "line_items": [
    {
      "line_number": 1,
      "description": "string",
      "quantity": "number as string",
      "unit_price": "number as string",
      "line_total": "number as string",
      "hsn_sac": "string or null"
    }
  ],
  "tax_lines": [
    {
      "line_number": 1,
      "description": "string",
      "taxable_value": "number as string",
      "rate": "number as string",
      "cgst": "number as string",
      "sgst": "number as string",
      "total_tax": "number as string"
    }
  ]
}

Important:
1. Do not enclose the JSON in markdown code blocks if possible, or return strictly valid JSON.
2. Monetary amounts must be formatted as strings (e.g. "1250.00").
3. Ensure every line item has a non-empty description, quantity, unit_price, and line_total.
"""


def _pv(val: Any, page: int = 1, confidence: float = 0.85) -> ProvenancedValue | None:
    if val is None or str(val).strip() == "":
        return None
    s_val = str(val).strip()
    return ProvenancedValue(
        value=normalize_locale(s_val, None),
        raw=s_val,
        page=page,
        bbox=None,
        confidence=confidence,
    )


def render_pages_to_jpeg(data: bytes, mime_type: str) -> list[bytes]:
    """Render PDF pages or raw image bytes to a list of JPEG byte buffers."""
    if mime_type in ("image/jpeg", "image/png", "image/webp"):
        return [data]

    images: list[bytes] = []
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            images.append(pix.tobytes("jpeg"))
    finally:
        doc.close()
    return images


class VlmExtractor(BaseExtractor):
    def __init__(self, gateway: NvidiaGateway | None = None) -> None:
        self.gateway = gateway or NvidiaGateway()

    def extract(self, data: bytes, mime_type: str) -> ExtractedDocument:
        images = render_pages_to_jpeg(data, mime_type)
        if not images:
            raise ValueError("No renderable pages found in document")

        response = self.gateway.extract(
            images=images,
            prompt=EXTRACTION_PROMPT,
            tenant_id="vlm_extractor",
        )

        parsed_data = self._clean_and_parse_json(response.content)
        return self._build_document(parsed_data, page_count=len(images))

    def _clean_and_parse_json(self, raw_content: str) -> dict[str, Any]:
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as err:
            logger.error("Failed to parse VLM response as JSON: %s\nContent: %s", err, raw_content)
            raise ValueError(f"Unparseable VLM response: {err}") from err

    def _build_document(self, data: dict[str, Any], page_count: int) -> ExtractedDocument:
        header_data = data.get("header", {})
        raw_doc_type = header_data.get("doc_type", "invoice")
        try:
            doc_type = DocumentType(raw_doc_type)
        except ValueError:
            doc_type = DocumentType.INVOICE

        header = DocumentHeader(
            document_id="vlm_doc",
            doc_type=doc_type,
            vendor_name=_pv(header_data.get("vendor_name")),
            vendor_address=_pv(header_data.get("vendor_address")),
            vendor_gstin=_pv(header_data.get("vendor_gstin")),
            buyer_name=_pv(header_data.get("buyer_name")),
            buyer_gstin=_pv(header_data.get("buyer_gstin")),
            invoice_date=_pv(header_data.get("invoice_date")),
            due_date=_pv(header_data.get("due_date")),
            po_reference=_pv(header_data.get("po_reference")),
            subtotal=_pv(header_data.get("subtotal")),
            grand_total=_pv(header_data.get("grand_total")),
            amount_in_words=_pv(header_data.get("amount_in_words")),
            bank_details=(
                header_data.get("bank_details")
                if isinstance(header_data.get("bank_details"), dict)
                else None
            ),
            order_date=_pv(header_data.get("order_date")),
            delivery_date=_pv(header_data.get("delivery_date")),
            grn_date=_pv(header_data.get("grn_date")),
        )

        line_items: list[LineItem] = []
        for idx, item in enumerate(data.get("line_items", []), start=1):
            if not isinstance(item, dict):
                continue
            desc = _pv(item.get("description"))
            qty = _pv(item.get("quantity"))
            price = _pv(item.get("unit_price") or item.get("rate"))
            total = _pv(item.get("line_total") or item.get("total"))
            if desc and qty and price and total:
                line_items.append(LineItem(
                    line_number=item.get("line_number", idx),
                    description=desc,
                    quantity=qty,
                    unit_price=price,
                    line_total=total,
                    hsn_sac=_pv(item.get("hsn_sac") or item.get("hsn")),
                ))

        tax_lines: list[TaxLine] = []
        for idx, tax in enumerate(data.get("tax_lines", []), start=1):
            if not isinstance(tax, dict):
                continue
            desc = _pv(tax.get("description"))
            taxable = _pv(tax.get("taxable_value"))
            rate = _pv(tax.get("rate"))
            cgst = _pv(tax.get("cgst"))
            sgst = _pv(tax.get("sgst"))
            total_tax = _pv(tax.get("total_tax"))
            if desc and taxable and rate and cgst and sgst and total_tax:
                tax_lines.append(TaxLine(
                    line_number=tax.get("line_number", idx),
                    description=desc,
                    taxable_value=taxable,
                    rate=rate,
                    cgst=cgst,
                    sgst=sgst,
                    total_tax=total_tax,
                ))

        coverage = Coverage(
            pages_total=page_count,
            pages_examined=page_count,
            coverage_complete=True,
        )
        return ExtractedDocument(
            document_id="vlm_doc",
            tenant_id="t",
            doc_type=doc_type,
            header=header,
            line_items=line_items,
            tax_lines=tax_lines,
            coverage=coverage,
            page_count=page_count,
            extractor_version="vlm_1.0.0",
        )

