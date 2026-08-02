from __future__ import annotations

from decimal import Decimal

import pytest

from audit_v2.domain.models import DocumentType, ExtractedDocument, ProvenancedValue

SAMPLE_PO_TEXT = """Purchase Order
PO No: PO-2026-0089
Order Date: 20/07/2026
Delivery Date: 15/08/2026
Vendor: Global Supplies Ltd
Vendor GSTIN: 29AABCT1234D1Z6
Address: 456 Industrial Zone, Pune - 411001
Delivery Address: Warehouse B, MIDC, Nashik - 422010
Payment Terms: 30 days from invoice

| # | Description          | HSN    | Qty | Rate    | Amount   |
|---|----------------------|--------|-----|---------|----------|
| 1 | Steel Rods 12mm      | 7214   | 100 | 450.00  | 45,000.00|
| 2 | Steel Rods 16mm      | 7214   | 50  | 520.00  | 26,000.00|

Total Order Value: 71,000.00
Amount in words: Rupees Seventy One Thousand Only
"""

SAMPLE_PO_NO_DELIVERY = """Purchase Order
PO No: PO-2026-0090
Order Date: 21/07/2026
Vendor: Acme Corp
Vendor GSTIN: 29AABCT1234D1Z6
Address: 123 Industrial Area, Pune

Total Order Value: 10,000.00
"""

SAMPLE_PO_NO_PAYMENT = """Purchase Order
PO No: PO-2026-0091
Order Date: 22/07/2026
Delivery Date: 16/08/2026
Vendor: Beta Ltd
Vendor GSTIN: 29AABCT1234D1Z6
Address: 789 Business Park, Mumbai

Total Amount: 25,000.00
Amount in words: Rupees Twenty Five Thousand Only
"""

SAMPLE_PO_VARIANT = """Purchase Order
PO/2026/0089
Order Date: 20/07/2026
Supplier: Global Supplies Ltd
GSTIN: 29AABCT1234D1Z6

Total Order Value: 71,000.00
"""


class TestPOExtractor:
    def test_extract_po_header(self):
        from audit_v2.extraction.po_extractor import POExtractor

        ext = POExtractor()
        header = ext._extract_header_from_text(SAMPLE_PO_TEXT)
        assert header.document_id == "PO-2026-0089"
        assert header.vendor_name is not None
        assert header.vendor_name.value == "Global Supplies Ltd"
        assert header.order_date is not None
        assert header.order_date.value == "2026-07-20"
        assert header.delivery_date is not None
        assert header.delivery_date.value == "2026-08-15"
        assert header.grand_total is not None
        assert header.grand_total.value == "71000.00"

    def test_extract_po_line_items(self):
        from audit_v2.extraction.po_extractor import POExtractor

        ext = POExtractor()
        items = ext._extract_line_items_from_text(SAMPLE_PO_TEXT)
        assert len(items) == 2
        assert items[0].line_number == 1
        assert items[0].description.value == "Steel Rods 12mm"
        assert items[0].quantity.decimal_value == Decimal(100)
        assert items[0].unit_price.decimal_value == Decimal("450.00")
        assert items[0].line_total.decimal_value == Decimal("45000.00")
        assert items[0].hsn_sac is not None
        assert items[0].hsn_sac.value == "7214"
        assert items[1].line_number == 2
        assert items[1].description.value == "Steel Rods 16mm"
        assert items[1].quantity.decimal_value == Decimal(50)
        assert items[1].line_total.decimal_value == Decimal("26000.00")

    def test_extract_po_full_document(self):
        from audit_v2.extraction.po_extractor import POExtractor

        ext = POExtractor()
        doc = ext.extract(SAMPLE_PO_TEXT.encode(), "text/plain")
        assert isinstance(doc, ExtractedDocument)
        assert doc.doc_type == DocumentType.PURCHASE_ORDER
        assert doc.document_id == "PO-2026-0089"
        assert len(doc.line_items) == 2
        assert doc.page_count == 1
        assert doc.extractor_version != ""

    def test_po_provenance_on_all_fields(self):
        from audit_v2.extraction.po_extractor import POExtractor

        ext = POExtractor()
        doc = ext.extract(SAMPLE_PO_TEXT.encode(), "text/plain")
        all_pvs: list[ProvenancedValue] = []
        if doc.header.vendor_name:
            all_pvs.append(doc.header.vendor_name)
        if doc.header.vendor_gstin:
            all_pvs.append(doc.header.vendor_gstin)
        if doc.header.order_date:
            all_pvs.append(doc.header.order_date)
        if doc.header.delivery_date:
            all_pvs.append(doc.header.delivery_date)
        if doc.header.grand_total:
            all_pvs.append(doc.header.grand_total)
        if doc.header.amount_in_words:
            all_pvs.append(doc.header.amount_in_words)
        if doc.header.payment_terms:
            all_pvs.append(doc.header.payment_terms)
        if doc.header.delivery_address:
            all_pvs.append(doc.header.delivery_address)
        for li in doc.line_items:
            all_pvs.extend([li.description, li.quantity, li.unit_price, li.line_total])
            if li.hsn_sac:
                all_pvs.append(li.hsn_sac)
        for pv in all_pvs:
            assert pv.value != "", f"Empty value in {pv}"
            assert pv.raw != "", f"Empty raw in {pv}"
            assert pv.page >= 1, f"Missing page in {pv}"

    def test_po_missing_delivery_date(self):
        from audit_v2.extraction.po_extractor import POExtractor

        ext = POExtractor()
        header = ext._extract_header_from_text(SAMPLE_PO_NO_DELIVERY)
        assert header.delivery_date is None

    def test_po_missing_payment_terms(self):
        from audit_v2.extraction.po_extractor import POExtractor

        ext = POExtractor()
        header = ext._extract_header_from_text(SAMPLE_PO_NO_PAYMENT)
        assert header.payment_terms is None

    def test_po_number_variants(self):
        from audit_v2.extraction.po_extractor import POExtractor

        ext = POExtractor()
        header = ext._extract_header_from_text(SAMPLE_PO_VARIANT)
        assert header.document_id is not None
        assert "2026" in header.document_id

    def test_po_no_tax_lines(self):
        from audit_v2.extraction.po_extractor import POExtractor

        ext = POExtractor()
        tax_lines = ext._extract_tax_lines_from_text(SAMPLE_PO_TEXT)
        assert tax_lines == []

    def test_extract_raises_on_empty_data(self):
        from audit_v2.extraction.po_extractor import POExtractor

        ext = POExtractor()
        with pytest.raises(ValueError):
            ext.extract(b"", "text/plain")

    def test_po_vendor_gstin_extracted(self):
        from audit_v2.extraction.po_extractor import POExtractor

        ext = POExtractor()
        header = ext._extract_header_from_text(SAMPLE_PO_TEXT)
        assert header.vendor_gstin is not None
        assert header.vendor_gstin.value == "29AABCT1234D1Z6"

    def test_po_vendor_address_extracted(self):
        from audit_v2.extraction.po_extractor import POExtractor

        ext = POExtractor()
        header = ext._extract_header_from_text(SAMPLE_PO_TEXT)
        assert header.vendor_address is not None
        assert "456 Industrial Zone" in header.vendor_address.value

    def test_po_amount_in_words_extracted(self):
        from audit_v2.extraction.po_extractor import POExtractor

        ext = POExtractor()
        header = ext._extract_header_from_text(SAMPLE_PO_TEXT)
        assert header.amount_in_words is not None
        assert "Seventy One Thousand" in header.amount_in_words.value
