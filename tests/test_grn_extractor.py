from __future__ import annotations

from decimal import Decimal

import pytest

from audit_v2.domain.models import DocumentType, ExtractedDocument, ProvenancedValue

SAMPLE_GRN_TEXT = """Goods Receipt Note
GRN No: GRN-2026-0032
Date: 25/07/2026
PO Reference: PO-2026-0089
DC Reference: DC-2026-0045
Vendor: Global Supplies Ltd
Inspected By: Suresh Patil

| # | Description          | HSN    | Ordered | Received | Rejected |
|---|----------------------|--------|---------|----------|----------|
| 1 | Steel Rods 12mm      | 7214   | 100     | 98       | 2        |
| 2 | Steel Rods 16mm      | 7214   | 50      | 50       | 0        |

Remarks: 2 rods damaged in transit
"""

SAMPLE_GRN_MISSING_PO = """Goods Receipt Note
GRN No: GRN-2026-0033
Date: 26/07/2026
Vendor: Acme Corp

| # | Description     | HSN    | Ordered | Received | Rejected |
|---|-----------------|--------|---------|----------|----------|
| 1 | Steel Rods 12mm | 7214   | 100     | 95       | 5        |

Remarks: partial delivery
"""

SAMPLE_GRN_MISSING_INSPECTED = """Goods Receipt Note
GRN No: GRN-2026-0034
Date: 27/07/2026
PO Reference: PO-2026-0091
Vendor: Beta Ltd

| # | Description     | HSN    | Ordered | Received | Rejected |
|---|-----------------|--------|---------|----------|----------|
| 1 | Nuts Bolts      | 7318   | 200     | 200      | 0        |

Remarks: OK
"""


class TestGRNExtractor:
    def test_extract_grn_header(self):
        from audit_v2.extraction.grn_extractor import GRNExtractor

        ext = GRNExtractor()
        header = ext._extract_header_from_text(SAMPLE_GRN_TEXT)
        assert header.document_id == "GRN-2026-0032"
        assert header.vendor_name is not None
        assert header.vendor_name.value == "Global Supplies Ltd"
        assert header.po_reference is not None
        assert header.po_reference.value == "PO-2026-0089"
        assert header.invoice_date is not None
        assert header.invoice_date.value == "2026-07-25"

    def test_extract_grn_line_items(self):
        from audit_v2.extraction.grn_extractor import GRNExtractor

        ext = GRNExtractor()
        items = ext._extract_line_items_from_text(SAMPLE_GRN_TEXT)
        assert len(items) == 2
        assert items[0].line_number == 1
        assert items[0].description.value == "Steel Rods 12mm"
        assert items[0].quantity.decimal_value == Decimal(98)
        assert items[0].unit_price.decimal_value == Decimal(0)
        assert items[0].line_total.decimal_value == Decimal(0)
        assert items[0].hsn_sac is not None
        assert items[0].hsn_sac.value == "7214"
        assert items[1].line_number == 2
        assert items[1].description.value == "Steel Rods 16mm"
        assert items[1].quantity.decimal_value == Decimal(50)

    def test_extract_grn_full_document(self):
        from audit_v2.extraction.grn_extractor import GRNExtractor

        ext = GRNExtractor()
        doc = ext.extract(SAMPLE_GRN_TEXT.encode(), "text/plain")
        assert isinstance(doc, ExtractedDocument)
        assert doc.doc_type == DocumentType.GOODS_RECEIPT_NOTE
        assert doc.document_id == "GRN-2026-0032"
        assert len(doc.line_items) == 2
        assert doc.page_count == 1
        assert doc.extractor_version != ""

    def test_grn_provenance_on_all_fields(self):
        from audit_v2.extraction.grn_extractor import GRNExtractor

        ext = GRNExtractor()
        doc = ext.extract(SAMPLE_GRN_TEXT.encode(), "text/plain")
        all_pvs: list[ProvenancedValue] = []
        if doc.header.vendor_name:
            all_pvs.append(doc.header.vendor_name)
        if doc.header.po_reference:
            all_pvs.append(doc.header.po_reference)
        if doc.header.invoice_date:
            all_pvs.append(doc.header.invoice_date)
        for li in doc.line_items:
            all_pvs.extend([li.description, li.quantity, li.unit_price, li.line_total])
            if li.hsn_sac:
                all_pvs.append(li.hsn_sac)
        for pv in all_pvs:
            assert pv.value != "", f"Empty value in {pv}"
            assert pv.raw is not None, f"None raw in {pv}"
            assert pv.page >= 1, f"Missing page in {pv}"

    def test_grn_missing_po_reference(self):
        from audit_v2.extraction.grn_extractor import GRNExtractor

        ext = GRNExtractor()
        header = ext._extract_header_from_text(SAMPLE_GRN_MISSING_PO)
        assert header.po_reference is None

    def test_grn_missing_inspected_by(self):
        from audit_v2.extraction.grn_extractor import GRNExtractor

        ext = GRNExtractor()
        doc = ext.extract(SAMPLE_GRN_MISSING_INSPECTED.encode(), "text/plain")
        assert doc.doc_type == DocumentType.GOODS_RECEIPT_NOTE
        assert doc.document_id == "GRN-2026-0034"

    def test_grn_no_tax_lines(self):
        from audit_v2.extraction.grn_extractor import GRNExtractor

        ext = GRNExtractor()
        tax_lines = ext._extract_tax_lines_from_text(SAMPLE_GRN_TEXT)
        assert tax_lines == []

    def test_extract_raises_on_empty_data(self):
        from audit_v2.extraction.grn_extractor import GRNExtractor

        ext = GRNExtractor()
        with pytest.raises(ValueError):
            ext.extract(b"", "text/plain")
