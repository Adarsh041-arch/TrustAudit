"""VLM-based document extractor — Phase 4 completion & Phase 5.1 (PHASES_V2 §4).

Uses NvidiaGateway to extract structured fields from scanned PDFs or image documents
where PyMuPDF text layer extraction fails or yields low confidence.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import fitz  # type: ignore[import-untyped]  # PyMuPDF has no bundled stubs

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
1. Output ONLY the raw JSON object. No prose, no explanation, no commentary,
   no markdown code fences — nothing before the opening { or after the closing }.
2. ALWAYS return the JSON object, even if the document is not one of the four
   types above or some fields are missing. Pick the closest doc_type and set any
   unknown field to null. Never refuse or reply that extraction is not possible.
3. Monetary amounts must be formatted as strings (e.g. "1250.00").
4. Ensure every line item has a non-empty description, quantity, unit_price, and line_total.

Respond with the JSON object only.
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


def _extract_json_object(text: str) -> str | None:
    """Return the first balanced ``{...}`` object embedded in ``text``, or None.

    Chatty vision models (e.g. meta/llama-3.2-vision) narrate around the JSON —
    "The provided document is an invoice... { ...json... }" — which json.loads
    rejects at char 0. Walk from the first ``{`` tracking brace depth while
    respecting string literals, so braces inside string values don't skew the
    count, and stop at the matching close brace (ignoring any trailing prose).
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None  # unbalanced — no complete object


def _normalize_parsed_vlm_dict(parsed: dict[str, Any]) -> dict[str, Any]:
    """Unwrap schemas or flat fields into the expected envelope."""
    if "properties" in parsed and isinstance(parsed["properties"], dict):
        props = parsed["properties"]
        if "header" in props:
            return props
        header_props = {k: v for k, v in props.items() if k not in ("line_items", "tax_lines")}
        items = props.get("line_items", [])
        tax = props.get("tax_lines", [])
        return {
            "header": header_props,
            "line_items": items if isinstance(items, list) else [],
            "tax_lines": tax if isinstance(tax, list) else [],
            **props,
        }
    return parsed


def _parse_markdown_kv(text: str) -> dict[str, Any] | None:
    """Fallback parser for chatty VLM replies formatted as Markdown key-value lists."""
    header: dict[str, Any] = {}
    line_items: list[dict[str, Any]] = []

    # Match lines like "* **Invoice Number**: PI-2026-453" or "**Seller**: ABC Agro"
    kv_pattern = re.compile(r"^\s*[*|-]?\s*\*\*?([^*:]+)\*\*?\s*:\s*(.+)$", re.MULTILINE)
    matches = kv_pattern.findall(text)
    if not matches:
        return None

    norm_map = {
        "invoice number": "invoice_number",
        "invoice no.": "invoice_number",
        "invoice id": "invoice_number",
        "purchase order number": "po_reference",
        "po number": "po_reference",
        "reference po": "po_reference",
        "reference contract": "contract_reference",
        "contract no.": "po_reference",
        "date": "invoice_date",
        "invoice date": "invoice_date",
        "order date": "order_date",
        "contract date": "invoice_date",
        "seller": "vendor_name",
        "vendor name": "vendor_name",
        "vendor": "vendor_name",
        "exporter": "vendor_name",
        "buyer": "buyer_name",
        "buyer name": "buyer_name",
        "consignee": "buyer_name",
        "grand total": "grand_total",
        "total invoice value": "grand_total",
        "amount": "grand_total",
        "contract value": "grand_total",
        "subtotal": "subtotal",
        "hs code": "hsn_sac",
        "hsn code": "hsn_sac",
    }

    item_desc = None
    item_qty = None
    item_price = None
    item_total = None
    item_hsn = None

    for raw_k, raw_v in matches:
        k = raw_k.strip().lower()
        v = raw_v.strip()
        if not v or v.lower() in ("not provided", "not applicable", "n/a", "none"):
            continue

        target_field = norm_map.get(k)
        if target_field:
            header[target_field] = v
        elif k in ("item description", "description of goods", "description"):
            item_desc = v
        elif "quantity" in k:
            item_qty = v
        elif "unit price" in k:
            item_price = v
        elif "line total" in k:
            item_total = v
        elif "hs code" in k or "hsn" in k:
            item_hsn = v

    if item_desc and (item_price or item_total):
        line_items.append({
            "line_number": 1,
            "description": item_desc,
            "quantity": item_qty or "1",
            "unit_price": item_price or item_total,
            "line_total": item_total or item_price,
            "hsn_sac": item_hsn,
        })

    if not header and not line_items:
        return None

    return {
        "header": header,
        "line_items": line_items,
        "tax_lines": [],
    }


def parse_vlm_json(raw_content: str) -> dict[str, Any]:
    """Parse a (possibly chatty / fenced) VLM reply into a JSON object.

    Handles the two ways vision models mangle JSON: markdown code fences, and
    prose narration wrapped around the object. Raises ``ValueError`` if no
    balanced JSON object can be recovered. Shared by :class:`VlmExtractor` and
    ``audit_v2.gateway.structured`` so both parse identically.
    """
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    # Try the whole (fence-stripped) string first, then the first balanced
    # {...} object embedded in prose. A chatty VLM often wraps valid JSON in
    # narration ("The provided document is an invoice... {json}"), which
    # json.loads rejects at char 0 even though the object is right there.
    candidates = [cleaned]
    embedded = _extract_json_object(cleaned)
    if embedded and embedded != cleaned:
        candidates.append(embedded)

    last_err: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as err:
            last_err = err
            continue
        if isinstance(parsed, dict):
            return _normalize_parsed_vlm_dict(parsed)
        # A bare array/scalar isn't the header/line_items envelope we need;
        # keep looking for an embedded object.
        last_err = last_err or json.JSONDecodeError(
            "expected a JSON object", candidate, 0
        )

    # Fallback: attempt to parse markdown key-value lines
    md_parsed = _parse_markdown_kv(raw_content)
    if md_parsed is not None:
        logger.info("Successfully parsed VLM reply via Markdown key-value fallback")
        return md_parsed

    logger.error(
        "Failed to parse VLM response as JSON: %s\nContent: %s", last_err, raw_content
    )
    raise ValueError(f"Unparseable VLM response: {last_err}") from last_err


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
        return parse_vlm_json(raw_content)

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
            # DocumentHeader normalizes null/empty sub-fields (see its validator).
            bank_details=header_data.get("bank_details"),
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

