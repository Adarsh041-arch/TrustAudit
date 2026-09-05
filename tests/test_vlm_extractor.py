"""Unit tests for VlmExtractor (PHASES_V2 §4 Phase 5.1)."""
from unittest.mock import MagicMock

import pytest

from audit_v2.domain.models import DocumentType
from audit_v2.extraction.vlm_extractor import VlmExtractor, _pv
from audit_v2.gateway.vlm_gateway import ModelResponse


class TestVlmExtractor:
    def test_clean_and_parse_json_markdown_blocks(self):
        ext = VlmExtractor(gateway=MagicMock())
        raw_markdown = '```json\n{"header": {"vendor_name": "Test Vendor"}}\n```'
        data = ext._clean_and_parse_json(raw_markdown)
        assert data["header"]["vendor_name"] == "Test Vendor"

    def test_clean_and_parse_json_prose_wrapped(self):
        """Regression: llama-3.2-vision narrates around the JSON object.

        Mirrors real server logs where the model returned a paragraph of prose
        followed by a valid JSON object; the old parser died at char 0.
        """
        ext = VlmExtractor(gateway=MagicMock())
        raw = (
            "The provided document is a commercial invoice, which includes the "
            "following information:\n\n**Header**\n\nBased on the extracted "
            "information, the JSON object is:\n\n"
            '{\n  "header": {"doc_type": "invoice", "grand_total": "525000.00"},\n'
            '  "line_items": [],\n  "tax_lines": []\n}\n\n'
            "Overall, the invoice appears to be a standard commercial invoice."
        )
        data = ext._clean_and_parse_json(raw)
        assert data["header"]["doc_type"] == "invoice"
        assert data["header"]["grand_total"] == "525000.00"

    def test_clean_and_parse_json_prose_wrapped_nested_object(self):
        """Brace-depth tracking must not stop at a nested object's close brace."""
        ext = VlmExtractor(gateway=MagicMock())
        raw = (
            "Here is the extracted data:\n"
            '{"header": {"bank_details": {"account_number": "123", "ifsc": "HDFC0001234"}, '
            '"vendor_name": "Acme"}, "line_items": [], "tax_lines": []}\n'
            "That concludes the extraction."
        )
        data = ext._clean_and_parse_json(raw)
        assert data["header"]["vendor_name"] == "Acme"
        assert data["header"]["bank_details"]["ifsc"] == "HDFC0001234"

    def test_clean_and_parse_json_invalid_raises_error(self):
        ext = VlmExtractor(gateway=MagicMock())
        with pytest.raises(ValueError, match="Unparseable VLM response"):
            ext._clean_and_parse_json("NOT VALID JSON")

    def test_clean_and_parse_json_schema_unwrapping(self):
        """Regression: model returns $defs and properties schema wrapper."""
        ext = VlmExtractor(gateway=MagicMock())
        raw = (
            '{"$defs": {"LineItemSchema": {}}, "properties": {'
            '"vendor_name": "ABC Agro", "invoice_number": "PI-2026-453", '
            '"grand_total": "525000.00", "line_items": [{"description": "Basmati", '
            '"quantity": "500", "unit_price": "1050", "line_total": "525000"}]}}'
        )
        data = ext._clean_and_parse_json(raw)
        assert data["header"]["vendor_name"] == "ABC Agro"
        assert data["header"]["invoice_number"] == "PI-2026-453"
        assert len(data["line_items"]) == 1

    def test_clean_and_parse_json_markdown_kv_fallback(self):
        """Fallback: vision model returns Markdown key-value list instead of JSON."""
        ext = VlmExtractor(gateway=MagicMock())
        raw_md = (
            "**Invoice Details**\n\n"
            "* **Invoice Number**: PI-2026-453\n"
            "* **Date**: 04 August 2026\n"
            "* **Seller**: ABC Agro Exports Pvt. Ltd.\n"
            "* **Buyer**: Green Valley Foods LLC\n"
            "* **Amount**: USD 525,000.00\n"
            "* **Item Description**: Premium Basmati Rice\n"
            "* **Quantity (MT)**: 500\n"
            "* **Unit Price**: USD 1,050.00\n"
        )
        data = ext._clean_and_parse_json(raw_md)
        assert data["header"]["invoice_number"] == "PI-2026-453"
        assert data["header"]["vendor_name"] == "ABC Agro Exports Pvt. Ltd."
        assert data["header"]["buyer_name"] == "Green Valley Foods LLC"
        assert data["header"]["grand_total"] == "USD 525,000.00"
        assert len(data["line_items"]) == 1
        assert data["line_items"][0]["description"] == "Premium Basmati Rice"

    def test_clean_and_parse_json_prose_without_json_raises(self):
        """A refusal with no JSON object or key-values still fails loudly."""
        ext = VlmExtractor(gateway=MagicMock())
        prose = "Unrelated text with no keys or structure"
        with pytest.raises(ValueError, match="Unparseable VLM response"):
            ext._clean_and_parse_json(prose)

    def test_pv_normalizes_thousand_separators(self):
        """Regression: nemotron emits '525,000.00'; decimal_value must not crash."""
        ext = VlmExtractor(gateway=MagicMock())
        data = {
            "header": {"doc_type": "invoice", "grand_total": "525,000.00"},
            "line_items": [],
            "tax_lines": [],
        }
        doc = ext._build_document(data, page_count=1)
        assert doc.header.grand_total is not None
        assert doc.header.grand_total.value == "525000.00"
        assert doc.header.grand_total.raw == "525,000.00"
        assert float(doc.header.grand_total.decimal_value) == 525000.0

    def test_pv_leaves_non_numeric_untouched(self):
        pv = _pv("Acme Solutions")
        assert pv is not None
        assert pv.value == "Acme Solutions"
        pv_date = _pv("2026-07-15")
        assert pv_date is not None
        assert pv_date.value == "2026-07-15"

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


class TestExtractStructured:
    """The structured-output path (new_requirements.md §2): guided_json →
    schema-in-prompt fallback → Pydantic validation → one correction retry."""

    VALID = '{"invoice_number": "INV-9", "grand_total": "100.00"}'

    def test_guided_success(self, make_gateway):
        from audit_v2.extraction.schemas import InvoiceExtraction
        from audit_v2.gateway.structured import extract_structured

        gw = make_gateway(self.VALID)
        result = extract_structured(
            gateway=gw, images=[b"img"], prompt="extract",
            schema_model=InvoiceExtraction, tenant_id="t",
        )
        assert isinstance(result, InvoiceExtraction)
        assert result.invoice_number == "INV-9"
        # A single guided call carrying the schema; no fallback needed.
        assert len(gw.calls) == 1
        assert gw.calls[0]["response_schema"] is not None

    def test_guided_rejected_falls_back_to_prompt(self, make_gateway):
        from audit_v2.extraction.schemas import InvoiceExtraction
        from audit_v2.gateway.structured import extract_structured

        # First (guided) call is rejected with a permanent RuntimeError (400/422);
        # the retry embeds the schema in the prompt with no response_schema.
        gw = make_gateway(RuntimeError("HTTP 400 guided_json unsupported"), self.VALID)
        result = extract_structured(
            gateway=gw, images=[b"img"], prompt="extract",
            schema_model=InvoiceExtraction, tenant_id="t",
        )
        assert result.grand_total == "100.00"
        assert len(gw.calls) == 2
        assert gw.calls[0]["response_schema"] is not None
        assert gw.calls[1]["response_schema"] is None
        assert "JSON Schema" in gw.calls[1]["prompt"]

    def test_validation_retry_then_success(self, make_gateway):
        from audit_v2.extraction.schemas import InvoiceExtraction
        from audit_v2.gateway.structured import extract_structured

        # First reply is unparseable; one correction round-trip recovers.
        gw = make_gateway("no json here", self.VALID)
        result = extract_structured(
            gateway=gw, images=[b"img"], prompt="extract",
            schema_model=InvoiceExtraction, tenant_id="t",
        )
        assert result.invoice_number == "INV-9"
        assert len(gw.calls) == 2
        assert "could not be used" in gw.calls[1]["prompt"]

    def test_unrecoverable_reply_raises(self, make_gateway):
        from audit_v2.extraction.schemas import InvoiceExtraction
        from audit_v2.gateway.structured import extract_structured

        gw = make_gateway("no json", "still no json")
        with pytest.raises(ValueError, match="Structured extraction failed"):
            extract_structured(
                gateway=gw, images=[b"img"], prompt="extract",
                schema_model=InvoiceExtraction, tenant_id="t",
            )
        assert len(gw.calls) == 2
