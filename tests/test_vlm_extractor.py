"""Unit tests for VlmExtractor (PHASES_V2 §4 Phase 5.1)."""
from unittest.mock import MagicMock

import pytest

from audit_v2.domain.models import DocumentType
from audit_v2.extraction.vlm_extractor import VlmExtractor
from audit_v2.gateway.vlm_gateway import ModelResponse


class TestVlmExtractor:
    def test_clean_and_parse_json_markdown_blocks(self):
        ext = VlmExtractor(gateway=MagicMock())
        raw_markdown = '```json\n{"header": {"vendor_name": "Test Vendor"}}\n```'
        data = ext._clean_and_parse_json(raw_markdown)
        assert data["header"]["vendor_name"] == "Test Vendor"

    def test_clean_and_parse_json_invalid_raises_error(self):
        ext = VlmExtractor(gateway=MagicMock())
        with pytest.raises(ValueError, match="Unparseable VLM response"):
            ext._clean_and_parse_json("NOT VALID JSON")

    def test_build_document_structure(self):
        ext = VlmExtractor(gateway=MagicMock())
        data = {
            "header": {
                "doc_type": "invoice",
                "vendor_name": "Acme Solutions",
                "vendor_gstin": "27AAACA12341Z5",
                "grand_total": "1180.00",
                "subtotal": "1000.00",
                "invoice_date": "2026-07-15",
            },
            "line_items": [
                {
                    "line_number": 1,
                    "description": "Widget A",
                    "quantity": "10",
                    "unit_price": "100.00",
                    "line_total": "1000.00",
                    "hsn_sac": "8471",
                }
            ],
            "tax_lines": [
                {
                    "line_number": 1,
                    "description": "CGST @ 9%",
                    "taxable_value": "1000.00",
                    "rate": "9",
                    "cgst": "90.00",
                    "sgst": "0.00",
                    "total_tax": "90.00",
                }
            ],
        }

        doc = ext._build_document(data, page_count=2)
        assert doc.doc_type == DocumentType.INVOICE
        assert doc.header.vendor_name is not None
        assert doc.header.vendor_name.value == "Acme Solutions"
        assert doc.header.grand_total is not None
        assert doc.header.grand_total.decimal_value == 1180.00
        assert len(doc.line_items) == 1
        assert doc.line_items[0].description.value == "Widget A"
        assert doc.line_items[0].line_total.decimal_value == 1000.00
        assert len(doc.tax_lines) == 1
        assert doc.coverage.pages_total == 2
        assert doc.coverage.pages_examined == 2
        assert doc.coverage.coverage_complete is True

    def test_extract_mocked_gateway(self, monkeypatch):
        mock_gw = MagicMock()
        mock_gw.extract.return_value = ModelResponse(
            content='{"header": {"doc_type": "purchase_order", "grand_total": "500.00"}}',
            model_version="mock-vlm",
        )
        ext = VlmExtractor(gateway=mock_gw)

        # Mock page rendering
        monkeypatch.setattr(
            "audit_v2.extraction.vlm_extractor.render_pages_to_jpeg",
            lambda data, mime_type: [b"fake_jpeg"],
        )

        doc = ext.extract(data=b"pdf_bytes", mime_type="application/pdf")
        assert doc.doc_type == DocumentType.PURCHASE_ORDER
        assert doc.header.grand_total is not None
        assert doc.header.grand_total.decimal_value == 500.00
        assert mock_gw.extract.called
