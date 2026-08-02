"""Tests for VlmTextExtractor (contract/letter VLM-only extraction)."""
from unittest.mock import MagicMock

import pytest

from audit_v2.domain.models import DocumentType
from audit_v2.extraction.text_doc_extractor import VlmTextExtractor
from audit_v2.gateway.vlm_gateway import ModelResponse


class TestVlmTextExtractor:
    def test_clean_and_parse_json_markdown_blocks(self):
        ext = VlmTextExtractor(gateway=MagicMock())
        raw = '```json\n{"header": {"party_a": "Acme"}}\n```'
        data = ext._clean_and_parse_json(raw)
        assert data["header"]["party_a"] == "Acme"

    def test_clean_and_parse_json_invalid_raises_error(self):
        ext = VlmTextExtractor(gateway=MagicMock())
        with pytest.raises(ValueError, match="Unparseable VLM text response"):
            ext._clean_and_parse_json("NOT VALID JSON")

    def test_build_contract_document(self):
        ext = VlmTextExtractor(gateway=MagicMock())
        data = {
            "header": {
                "doc_type": "contract",
                "party_a": "Acme Solutions",
                "party_b": "Beta Ltd",
                "date": "2026-07-15",
                "expiry_date": "2027-07-14",
                "reference": "CON-2026-001",
                "value_amount": "500000.00",
                "subject": "Supply agreement",
            },
            "narrative_report": "Supply agreement between Acme and Beta, "
                                "valid 1 year, value 500000.00.",
        }
        doc = ext._build_document(data, page_count=3)
        assert doc.doc_type == DocumentType.CONTRACT
        assert doc.header.vendor_name.value == "Acme Solutions"
        assert doc.header.buyer_name.value == "Beta Ltd"
        assert doc.header.expiry_date is not None
        assert doc.header.grand_total.decimal_value == 500000.00
        assert doc.narrative_report.startswith("Supply agreement")
        assert doc.line_items == []
        assert doc.coverage.coverage_complete is True

    def test_build_letter_document_defaults(self):
        ext = VlmTextExtractor(gateway=MagicMock())
        data = {"header": {"party_a": "Sender"}, "narrative_report": "Memo."}
        doc = ext._build_document(data, page_count=1)
        assert doc.doc_type == DocumentType.CONTRACT
        assert doc.narrative_report == "Memo."

    def test_extract_mocked_gateway(self, monkeypatch):
        mock_gw = MagicMock()
        mock_gw.extract.return_value = ModelResponse(
            content=(
                '{"header": {"doc_type": "contract", "party_a": "Acme"},'
                ' "narrative_report": "Contract."}'
            ),
            model_version="mock-vlm",
        )
        ext = VlmTextExtractor(gateway=mock_gw)
        monkeypatch.setattr(
            "audit_v2.extraction.text_doc_extractor.render_pages_to_jpeg",
            lambda data, mime_type: [b"fake_jpeg"],
        )
        doc = ext.extract(data=b"pdf_bytes", mime_type="application/pdf")
        assert doc.doc_type == DocumentType.CONTRACT
        assert doc.header.vendor_name.value == "Acme"
        assert doc.narrative_report == "Contract."
        assert mock_gw.extract.called
