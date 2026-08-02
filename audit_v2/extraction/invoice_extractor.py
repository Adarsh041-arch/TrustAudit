from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

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
from audit_v2.extraction.parser import (
    parse_amount,
    parse_date,
    validate_gstin,
)
from audit_v2.extraction.text_extractor import TextExtractor

HEADER_FIELD_PATTERNS: dict[str, re.Pattern] = {
    "vendor_name": re.compile(
        r"(?:Seller|Vendor|Supplier|From)\s*:?\s*(.+?)(?:\n|$)", re.IGNORECASE
    ),
    "vendor_gstin": re.compile(
        r"(?:GSTIN?|GST\s*IN?|GST\s*No)\s*:?\s*([0-9A-Za-z]{15})\b"
    ),
    "vendor_address": re.compile(
        r"(?:Address|Addr)\s*:?\s*(.+?)(?:\n|$)", re.IGNORECASE
    ),
    "buyer_name": re.compile(
        r"(?:Buyer|Bill\s*To|Ship\s*To|Customer|Consignee)\s*:?\s*"
        r"(?:\n|\t)*(?:Name\s*:\s*)?[\t ]*(.+?)(?:\n|\t|$)",
        re.IGNORECASE,
    ),
    "buyer_gstin": re.compile(
        r"(?:Buyer\s*GSTIN?|Bill\s*To\s*GST)\s*:?\s*([0-9A-Za-z]{15})\b"
    ),
    "invoice_number": re.compile(
        r"(?:Invoice\s*(?:No|Number|#)|Inv\s*No)\s*:?\s*([A-Za-z0-9/-]+)",
        re.IGNORECASE,
    ),
    "invoice_date": re.compile(
        r"(?:Invoice\s*Date|Date|Dated)\s*:?\s*([0-9/.-]+(?:\s*[A-Za-z]+\s*[0-9]{4})?)",
        re.IGNORECASE,
    ),
    "po_reference": re.compile(
        # \b guards: without them "PO" matches inside "24-port", capturing "rt".
        r"\b(?:PO|P\.?O\.?|Purchase\s*Order)\b\s*"
        r"(?:No|Number|#|Reference|Ref)?\.?\s*:\s*([A-Za-z0-9][A-Za-z0-9/-]*)",
        re.IGNORECASE,
    ),
    "grand_total": re.compile(
        r"(?:Grand\s*Total|Net\s*Amount|Amount\s*Payable|Total\s*Payable)"
        r"\s*:?\s*\|?\s*(?:INR|Rs\.?|₹|\$|€|£)*\s*([0-9][0-9,]*\.?\d*)",
        re.IGNORECASE,
    ),
    "amount_in_words": re.compile(
        r"(?:Amount\s*in\s*words|Rupees|In\s*Words)\s*:?\s*(.+?)(?:\n|$)",
        re.IGNORECASE,
    ),
}

LINE_ITEM_TABLE_RE = re.compile(
    r"^\s*\|?\s*[#]?\s*(?:Sr|Sl|No|#)\s*.*?(?:Description|Item|Product)\s*.*?(?:HSN|SAC|Code)?\s*.*?"
    r"(?:Qty|Quantity)\s*.*?(?:Rate|Price|Unit\s*Price)\s*.*?(?:Amount|Total|Value)\s*.*?$",
    re.IGNORECASE | re.MULTILINE,
)

LINE_ITEM_ROW_RE = re.compile(
    r"\s*\|?\s*(?:(?P<num>\d+)\s*\|?\s*)?"
    r"(?P<desc>[A-Za-z][A-Za-z0-9\s/&-]+?)\s*\|?\s*"
    r"(?:(?P<hsn>\d{4,8})\s*\|?\s*)?"
    r"(?P<qty>[0-9,]+\.?\d*)\s*\|?\s*"
    r"(?P<rate>[0-9,]+\.?\d*)\s*\|?\s*"
    r"(?P<amount>[0-9,]+\.?\d*)\s*\|?\s*",
    re.IGNORECASE,
)

TAX_LINE_RE = re.compile(
    r"(?P<name>CGST|SGST|IGST|UTGST|Cess)\s*"
    r"(?:\(?\s*@?\s*(?P<rate>\d+\.?\d*)\s*%\s*\)?)?"
    r"[^\n\d]*?(?:INR|Rs\.?|₹|\$|€|£)?\s*(?P<amount>[0-9][0-9,]*\.\d{2})",
    re.IGNORECASE,
)

TAX_SUMMARY_RE = re.compile(
    r"(?:Total\s*Tax|Tax\s*Amount)\s*:?\s*[₹$\€£]*\s*(?P<total>[0-9,]+\.?\d*)",
    re.IGNORECASE,
)

SUBTOTAL_RE = re.compile(
    r"(?:Subtotal|Sub\s*Total|Total\s*Taxable\s*Value|Taxable\s*(?:Value|Amount))"
    r"[^\n]*?(?:INR|Rs\.?|₹|\$|€|£)*\s*([0-9][0-9,]*\.\d{2})",
    re.IGNORECASE,
)

BANK_ACCOUNT_RE = re.compile(
    r"(?:A/?c\.?\s*(?:No|Number)?|Account\s*(?:No|Number)?)\s*:?\s*\|?\s*(\d[\d\s-]{6,})",
    re.IGNORECASE,
)
BANK_IFSC_RE = re.compile(r"IFSC\s*(?:Code)?\s*:?\s*\|?\s*([A-Z]{4}0[A-Z0-9]{6})", re.IGNORECASE)
BANK_NAME_RE = re.compile(
    r"Bank\s*(?:Name)?\s*:\s*\|?\s*([A-Za-z][A-Za-z .&-]{3,})", re.IGNORECASE
)


class InvoiceExtractor(BaseExtractor):
    def __init__(self):
        self._text_extractor = TextExtractor()

    def extract(self, data: bytes, mime_type: str) -> ExtractedDocument:
        if not data:
            raise ValueError("Empty data provided for extraction")

        text_blocks: list[dict[str, Any]] = []
        page_texts: dict[int, str] = {}
        total_pages = 1

        if mime_type == "text/plain":
            text = data.decode("utf-8", errors="replace")
            total_pages = 1
        elif mime_type == "application/pdf":
            text_blocks = self._text_extractor.extract_text_blocks(data)
            page_texts = self._text_extractor.extract_page_texts(data)
            text = "\n".join(page_texts.values())
            page_nums = sorted(page_texts.keys())
            total_pages = page_nums[-1] if page_nums else 1
        else:
            text = ""

        if not text.strip():
            raise ValueError("No extractable text found in document")

        header = self._extract_header_from_text(text, text_blocks)
        line_items = self._extract_line_items_from_text(text, text_blocks)
        tax_lines = self._extract_tax_lines_from_text(text, text_blocks, header)

        if not header.document_id or header.document_id == "extracted":
            header.document_id = "inv_extracted"

        if mime_type == "application/pdf" and text_blocks:
            pages_with_text = len(page_texts)
            all_page_nums = set(range(1, total_pages + 1))
            pages_with_text_set = set(page_texts.keys())
            unreadable = sorted(all_page_nums - pages_with_text_set)
            coverage = Coverage(
                pages_total=total_pages,
                pages_examined=pages_with_text,
                pages_unreadable=unreadable,
                coverage_complete=pages_with_text == total_pages,
            )
        else:
            coverage = Coverage(
                pages_total=1,
                pages_examined=1,
                pages_unreadable=[],
                coverage_complete=True,
            )

        return ExtractedDocument(
            document_id=header.document_id or "inv_extracted",
            tenant_id="extracted",
            doc_type=DocumentType.INVOICE,
            header=header,
            line_items=line_items,
            tax_lines=tax_lines,
            coverage=coverage,
            page_count=total_pages,
            extractor_version="2.1.0",
        )

    def _find_block_for(
        self, raw: str, text_blocks: list[dict[str, Any]]
    ) -> tuple[int, list[float] | None]:
        for block in text_blocks:
            if raw in block.get("text", ""):
                return block.get("page", 1), block.get("bbox")
        return 1, None

    def _extract_header_from_text(
        self, text: str, text_blocks: list[dict[str, Any]] | None = None,
    ) -> DocumentHeader:
        blocks = text_blocks or []
        header = DocumentHeader(document_id="inv_extracted", doc_type=DocumentType.INVOICE)

        for field, pattern in HEADER_FIELD_PATTERNS.items():
            m = pattern.search(text)
            if not m:
                continue
            raw_value = m.group(1).strip()
            if not raw_value:
                continue

            page, bbox = self._find_block_for(raw_value, blocks)

            if field == "invoice_date":
                parsed = parse_date(raw_value)
                if parsed:
                    setattr(header, field, ProvenancedValue(
                        value=parsed.isoformat(),
                        raw=raw_value,
                        bbox=bbox,
                        page=page,
                        confidence=0.90,
                    ))
            elif field == "vendor_gstin" or field == "buyer_gstin":
                gstin = raw_value.upper()
                if validate_gstin(gstin):
                    setattr(header, field, ProvenancedValue(
                        value=gstin,
                        raw=raw_value,
                        bbox=bbox,
                        page=page,
                        confidence=0.95,
                    ))
            elif field == "grand_total":
                parsed_amount = parse_amount(raw_value, "en-IN")
                if parsed_amount:
                    setattr(header, field, ProvenancedValue(
                        value=str(parsed_amount),
                        raw=raw_value,
                        bbox=bbox,
                        page=page,
                        confidence=0.90,
                    ))
            elif field == "po_reference":
                setattr(header, field, ProvenancedValue(
                    value=raw_value,
                    raw=raw_value,
                    bbox=bbox,
                    page=page,
                    confidence=0.85,
                ))
            elif field == "amount_in_words":
                setattr(header, field, ProvenancedValue(
                    value=raw_value,
                    raw=raw_value,
                    bbox=bbox,
                    page=page,
                    confidence=0.80,
                ))
            elif field in ("vendor_name", "vendor_address", "buyer_name"):
                setattr(header, field, ProvenancedValue(
                    value=raw_value,
                    raw=raw_value,
                    bbox=bbox,
                    page=page,
                    confidence=0.90,
                ))
            elif field == "invoice_number":
                header.document_id = raw_value

        self._extract_subtotal(header, text, blocks)
        self._extract_bank_details(header, text)
        if header.vendor_name is None:
            self._infer_vendor_name(header, blocks)
        return header

    # Indian invoices commonly print the seller's name as the masthead with no
    # "Seller:" label, so fall back to the first non-title block on page 1.
    _MASTHEAD_SKIP = re.compile(r"^(tax\s+invoice|invoice|proforma|bill)\b", re.IGNORECASE)

    def _infer_vendor_name(
        self, header: DocumentHeader, blocks: list[dict[str, Any]],
    ) -> None:
        for block in blocks:
            if block.get("page", 1) != 1:
                continue
            candidate = block.get("text", "").split("\t")[0].strip()
            if not candidate or self._MASTHEAD_SKIP.match(candidate):
                continue
            if not re.match(r"^[A-Za-z]", candidate):
                continue
            header.vendor_name = ProvenancedValue(
                value=candidate,
                raw=candidate,
                bbox=block.get("bbox"),
                page=block.get("page", 1),
                confidence=0.70,
            )
            return

    def _extract_subtotal(
        self, header: DocumentHeader, text: str, blocks: list[dict[str, Any]],
    ) -> None:
        m = SUBTOTAL_RE.search(text)
        if not m:
            return
        raw_value = m.group(1).strip()
        parsed = parse_amount(raw_value, "en-IN")
        if parsed is None:
            return
        page, bbox = self._find_block_for(raw_value, blocks)
        header.subtotal = ProvenancedValue(
            value=str(parsed), raw=raw_value, bbox=bbox, page=page, confidence=0.90,
        )

    def _extract_bank_details(self, header: DocumentHeader, text: str) -> None:
        details: dict[str, str] = {}
        acct = BANK_ACCOUNT_RE.search(text)
        if acct:
            details["account_number"] = re.sub(r"[\s-]", "", acct.group(1))
        ifsc = BANK_IFSC_RE.search(text)
        if ifsc:
            details["ifsc"] = ifsc.group(1).upper()
        name = BANK_NAME_RE.search(text)
        if name:
            details["bank_name"] = name.group(1).strip()
        if details:
            header.bank_details = details

    TABLE_END_MARKERS = re.compile(
        r"^(?:Taxable\s*(?:Value|Amount)|Subtotal|Total\s*Tax|Grand\s*Total|Total|Net\s*Amount)",
        re.IGNORECASE,
    )

    def _extract_line_items_from_text(
        self, text: str, text_blocks: list[dict[str, Any]] | None = None,
    ) -> list[LineItem]:
        items: list[LineItem] = []
        blocks = text_blocks or []
        lines = text.splitlines()
        found_header = False

        for line_text in lines:
            stripped = line_text.strip()
            if not stripped:
                continue

            if not found_header and LINE_ITEM_TABLE_RE.match(stripped):
                found_header = True
                continue

            if not found_header:
                continue

            if self.TABLE_END_MARKERS.match(stripped):
                break

            m = LINE_ITEM_ROW_RE.search(stripped)
            if not m:
                continue

            desc = m.group("desc").strip()
            qty_raw = m.group("qty")
            rate_raw = m.group("rate")
            amount_raw = m.group("amount")
            hsn_raw = m.group("hsn")
            num_raw = m.group("num")

            qty = parse_amount(qty_raw, "en-IN")
            rate = parse_amount(rate_raw, "en-IN")
            amount = parse_amount(amount_raw, "en-IN")

            if qty is None or rate is None or amount is None:
                continue

            desc_page, desc_bbox = self._find_block_for(desc, blocks)

            item = LineItem(
                line_number=int(num_raw) if num_raw else (len(items) + 1),
                description=ProvenancedValue(
                    value=desc, raw=desc, bbox=desc_bbox, page=desc_page, confidence=0.90,
                ),
                quantity=ProvenancedValue(
                    value=str(qty), raw=qty_raw, page=desc_page, confidence=0.95,
                ),
                unit_price=ProvenancedValue(
                    value=str(rate), raw=rate_raw, page=desc_page, confidence=0.95,
                ),
                line_total=ProvenancedValue(
                    value=str(amount), raw=amount_raw, page=desc_page, confidence=0.95,
                ),
                hsn_sac=(
                    ProvenancedValue(value=hsn_raw, raw=hsn_raw, page=desc_page, confidence=0.85)
                    if hsn_raw else None
                ),
            )
            items.append(item)

        return items

    def _extract_tax_lines_from_text(
        self, text: str, text_blocks: list[dict[str, Any]] | None = None,
        header: DocumentHeader | None = None,
    ) -> list[TaxLine]:
        tax_lines: list[TaxLine] = []

        # GST is levied on the taxable value, which for a single-rate invoice is
        # the subtotal. Leaving it at "0" makes CHK-ARITH-TAX-002 unverifiable.
        if header is not None and header.subtotal is not None:
            taxable_pv = ProvenancedValue(
                value=header.subtotal.value,
                raw=header.subtotal.raw,
                bbox=header.subtotal.bbox,
                page=header.subtotal.page,
                confidence=0.75,
            )
        else:
            taxable_pv = ProvenancedValue(value="0", raw="", page=1, confidence=0.30)

        for line_num, m in enumerate(TAX_LINE_RE.finditer(text), start=1):
            name = m.group("name")
            rate_raw = m.group("rate")
            amount_raw = m.group("amount")

            rate = parse_amount(rate_raw, "en-IN") if rate_raw else Decimal("0")
            amount = parse_amount(amount_raw, "en-IN") if amount_raw else Decimal("0")

            name_pv = ProvenancedValue(value=name, raw=m.group(0), page=1, confidence=0.90)
            rate_pv = ProvenancedValue(value=str(rate), raw=rate_raw or "", page=1, confidence=0.85)
            amount_pv = ProvenancedValue(value=str(amount), raw=amount_raw, page=1, confidence=0.90)
            zero_pv = ProvenancedValue(value="0", raw="", page=1, confidence=0.50)

            if "CGST" in name.upper():
                tax_line = TaxLine(
                    line_number=line_num,
                    description=name_pv,
                    taxable_value=taxable_pv,
                    rate=rate_pv,
                    cgst=amount_pv,
                    sgst=zero_pv,
                    total_tax=amount_pv,
                )
            elif "SGST" in name.upper():
                tax_line = TaxLine(
                    line_number=line_num,
                    description=name_pv,
                    taxable_value=taxable_pv,
                    rate=rate_pv,
                    cgst=zero_pv,
                    sgst=amount_pv,
                    total_tax=amount_pv,
                )
            else:
                tax_line = TaxLine(
                    line_number=line_num,
                    description=name_pv,
                    taxable_value=taxable_pv,
                    rate=rate_pv,
                    cgst=zero_pv,
                    sgst=zero_pv,
                    total_tax=amount_pv,
                )

            tax_lines.append(tax_line)

        return tax_lines
