from __future__ import annotations

from decimal import Decimal

from audit_v2.domain.models import DocumentType, ExtractedDocument, ProvenancedValue

SAMPLE_DC_TEXT = """Delivery Challan
DC No: DC-2026-0045
Date: 22/07/2026
PO Reference: PO-2026-0089
Vehicle No: MH-01-AB-5678
From: Global Supplies Ltd, Pune
To: Warehouse B, MIDC, Nashik

| # | Description          | HSN    | Qty Delivered | Unit |
|---|----------------------|--------|---------------|------|
| 1 | Steel Rods 12mm      | 7214   | 100           | Pcs  |
| 2 | Steel Rods 16mm      | 7214   | 50            | Pcs  |

Remarks: Material in good condition
Received By: Rajesh Kumar
"""

SAMPLE_DC_NO_PO = """Delivery Challan
DC No: DC-2026-0046
Date: 23/07/2026
From: Global Supplies Ltd, Pune

| # | Description          | HSN    | Qty Delivered | Unit |
|---|----------------------|--------|---------------|------|
| 1 | Steel Rods 12mm      | 7214   | 100           | Pcs  |

Remarks: OK
"""

SAMPLE_DC_NO_VEHICLE = """Delivery Challan
DC No: DC-2026-0047
Date: 24/07/2026
PO Reference: PO-2026-0090
From: Global Supplies Ltd, Pune

| # | Description          | HSN    | Qty Delivered | Unit |
|---|----------------------|--------|---------------|------|
| 1 | Steel Rods 12mm      | 7214   | 100           | Pcs  |

Remarks: OK
"""


class TestDCExtractor:
    def test_extract_dc_header(self):
        from audit_v2.extraction.delivery_challan_extractor import (
            DeliveryChallanExtractor,
        )

        ext = DeliveryChallanExtractor()
        header = ext._extract_header_from_text(SAMPLE_DC_TEXT)
        assert header.document_id == "DC-2026-0045"
        assert header.vendor_name is not None
        assert header.vendor_name.value == "Global Supplies Ltd, Pune"
        assert header.po_reference is not None
        assert header.po_reference.value == "PO-2026-0089"
        assert header.delivery_date is not None
        assert header.delivery_date.value == "2026-07-22"

    def test_extract_dc_line_items(self):
        from audit_v2.extraction.delivery_challan_extractor import (
            DeliveryChallanExtractor,
        )

        ext = DeliveryChallanExtractor()
        items = ext._extract_line_items_from_text(SAMPLE_DC_TEXT)
        assert len(items) == 2
        assert items[0].line_number == 1
        assert items[0].description.value == "Steel Rods 12mm"
        assert items[0].quantity.decimal_value == Decimal(100)
        assert items[1].line_number == 2
        assert items[1].description.value == "Steel Rods 16mm"
        assert items[1].quantity.decimal_value == Decimal(50)

    def test_extract_dc_full_document(self):
        from audit_v2.extraction.delivery_challan_extractor import (
            DeliveryChallanExtractor,
        )

        ext = DeliveryChallanExtractor()
        doc = ext.extract(SAMPLE_DC_TEXT.encode(), "text/plain")
        assert isinstance(doc, ExtractedDocument)
        assert doc.doc_type == DocumentType.DELIVERY_CHALLAN
        assert doc.document_id == "DC-2026-0045"
        assert len(doc.line_items) == 2
        assert doc.page_count == 1
        assert doc.extractor_version != ""

    def test_dc_provenance_on_all_fields(self):
        from audit_v2.extraction.delivery_challan_extractor import (
            DeliveryChallanExtractor,
        )

        ext = DeliveryChallanExtractor()
        doc = ext.extract(SAMPLE_DC_TEXT.encode(), "text/plain")
        all_pvs: list[ProvenancedValue] = []
        if doc.header.vendor_name:
            all_pvs.append(doc.header.vendor_name)
        if doc.header.po_reference:
            all_pvs.append(doc.header.po_reference)
        if doc.header.delivery_date:
            all_pvs.append(doc.header.delivery_date)
        if doc.header.buyer_name:
            all_pvs.append(doc.header.buyer_name)
        for li in doc.line_items:
            all_pvs.extend([li.description, li.quantity, li.unit_price, li.line_total])
            if li.hsn_sac:
                all_pvs.append(li.hsn_sac)
        for pv in all_pvs:
            assert pv.value is not None, f"None value in {pv}"
            assert pv.raw is not None, f"None raw in {pv}"
            assert pv.page >= 1, f"Missing page in {pv}"

    def test_dc_missing_po_reference(self):
        from audit_v2.extraction.delivery_challan_extractor import (
            DeliveryChallanExtractor,
        )

        ext = DeliveryChallanExtractor()
        header = ext._extract_header_from_text(SAMPLE_DC_NO_PO)
        assert header.po_reference is None

    def test_dc_missing_vehicle_number(self):
        from audit_v2.extraction.delivery_challan_extractor import (
            DeliveryChallanExtractor,
        )

        ext = DeliveryChallanExtractor()
        doc = ext.extract(SAMPLE_DC_NO_VEHICLE.encode(), "text/plain")
        assert doc.doc_type == DocumentType.DELIVERY_CHALLAN
        assert doc.document_id == "DC-2026-0047"

    def test_dc_no_tax_lines(self):
        from audit_v2.extraction.delivery_challan_extractor import (
            DeliveryChallanExtractor,
        )

        ext = DeliveryChallanExtractor()
        tax_lines = ext._extract_tax_lines_from_text(SAMPLE_DC_TEXT)
        assert tax_lines == []
