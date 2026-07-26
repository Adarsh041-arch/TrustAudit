from __future__ import annotations

import re
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
)
from audit_v2.extraction.text_extractor import TextExtractor

HEADER_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "grn_number": re.compile(
        r"(?:GRN\s*(?:No|Number|#)|Goods\s+Receipt\s+Note\s*(?:No|Number|#))\s*:?\s*([A-Za-z0-9/-]+)",
        re.IGNORECASE,
    ),
    "po_reference": re.compile(
        r"(?:PO\s*(?:Reference|Ref)|Against\s+PO)\s*:?\s*([A-Za-z0-9/-]+)",
        re.IGNORECASE,
    ),
    "dc_reference": re.compile(
        r"DC\s*(?:Reference|Ref)\s*:?\s*([A-Za-z0-9/-]+)",
        re.IGNORECASE,
    ),
    "vendor_name": re.compile(
        r"(?:Vendor|Supplier|From)\s*:?\s*(.+?)(?:\n|$)", re.IGNORECASE
    ),
    "invoice_date": re.compile(
        r"(?:(?:GRN\s*)?Date|Received\s*Date)\s*:?\s*([0-9/.-]+(?:\s*[A-Za-z]+\s*[0-9]{4})?)",
        re.IGNORECASE,
    ),
    "inspected_by": re.compile(
        r"(?:Inspected\s*By|Inspected|Checked\s*By)\s*:?\s*(.+?)(?:\n|$)", re.IGNORECASE
    ),
    "remarks": re.compile(
        r"Remarks\s*:?\s*(.*?)(?:\n|$)", re.IGNORECASE
    ),
}

LINE_ITEM_TABLE_RE = re.compile(
    r"^\s*\|?\s*[#]?\s*(?:Sr|Sl|No|#)\s*.*?(?:Description|Item|Product)\s*.*?(?:HSN|SAC|Code)?\s*.*?"
    r"(?:Ordered|Order)\s*.*?(?:Received|Receipt)\s*.*?(?:Rejected|Reject)\s*.*?$",
    re.IGNORECASE | re.MULTILINE,
)

LINE_ITEM_ROW_RE = re.compile(
    r"\s*\|\s*(?:(?P<num>\d+)\s*\|\s*)?"
    r"(?P<desc>[A-Za-z][A-Za-z0-9\s/&-]+?)\s*\|\s*"
    r"(?:(?P<hsn>\d{4,8})\s*\|\s*)?"
    r"(?P<qty_ordered>[0-9,]+\.?\d*)\s*\|\s*"
    r"(?P<qty_received>[0-9,]+\.?\d*)\s*\|\s*"
    r"(?P<qty_rejected>[0-9,]+\.?\d*)\s*\|",
    re.IGNORECASE,
)


class GRNExtractor(BaseExtractor):
    def __init__(self) -> None:
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
        tax_lines = self._extract_tax_lines_from_text(text, text_blocks)

        if not header.document_id or header.document_id == "extracted":
            header.document_id = "grn_extracted"

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
            document_id=header.document_id or "grn_extracted",
            tenant_id="extracted",
            doc_type=DocumentType.GOODS_RECEIPT_NOTE,
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
        header = DocumentHeader(
            document_id="grn_extracted", doc_type=DocumentType.GOODS_RECEIPT_NOTE,
        )

        for field, pattern in HEADER_FIELD_PATTERNS.items():
            m = pattern.search(text)
            if not m:
                continue
            raw_value = m.group(1).strip()
            if not raw_value:
                continue

            page, bbox = self._find_block_for(raw_value, blocks)

            if field == "grn_number":
                header.document_id = raw_value

            elif field == "invoice_date":
                # A GRN's document date IS its receipt date — that is the field
                # CHK-FORMAT-MANDATORY-001 and CHK-TEMP-DELIVERY-001 read.
                parsed = parse_date(raw_value)
                if parsed:
                    header.grn_date = ProvenancedValue(
                        value=parsed.isoformat(),
                        raw=raw_value,
                        bbox=bbox,
                        page=page,
                        confidence=0.90,
                    )

            elif field == "vendor_name":
                header.vendor_name = ProvenancedValue(
                    value=raw_value,
                    raw=raw_value,
                    bbox=bbox,
                    page=page,
                    confidence=0.90,
                )

            elif field == "po_reference":
                header.po_reference = ProvenancedValue(
                    value=raw_value,
                    raw=raw_value,
                    bbox=bbox,
                    page=page,
                    confidence=0.85,
                )

        return header

    TABLE_END_MARKERS = re.compile(
        r"^(?:Remarks|Total|Inspected\s*By|Certified)",
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
            qty_received_raw = m.group("qty_received")
            qty_rejected_raw = m.group("qty_rejected")  # noqa: F841  # TODO: store when model has rejected_qty field
            hsn_raw = m.group("hsn")
            num_raw = m.group("num")

            qty_received = parse_amount(qty_received_raw, "en-IN")

            if qty_received is None:
                continue

            desc_page, desc_bbox = self._find_block_for(desc, blocks)

            item = LineItem(
                line_number=int(num_raw) if num_raw else (len(items) + 1),
                description=ProvenancedValue(
                    value=desc, raw=desc, bbox=desc_bbox, page=desc_page, confidence=0.90,
                ),
                quantity=ProvenancedValue(
                    value=str(qty_received), raw=qty_received_raw, page=desc_page, confidence=0.95,
                ),
                unit_price=ProvenancedValue(
                    value="0", raw="", page=desc_page, confidence=0.50,
                ),
                line_total=ProvenancedValue(
                    value="0", raw="", page=desc_page, confidence=0.50,
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
    ) -> list[TaxLine]:
        return []
