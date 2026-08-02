"""Tests for the dual-extraction merge engine (audit_v2/extraction/merge.py)."""
from audit_v2.domain.models import (
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
    LineItem,
    ProvenancedValue,
    TaxLine,
)
from audit_v2.extraction.merge import merge_extractions


def _pv(value: str, confidence: float = 0.9) -> ProvenancedValue:
    return ProvenancedValue(value=value, raw=value, confidence=confidence)


def _doc(
    doc_type: DocumentType = DocumentType.INVOICE,
    vendor: str | None = "Acme",
    grand_total: str | None = "1000.00",
    lines: list[LineItem] | None = None,
    tax_lines: list[TaxLine] | None = None,
) -> ExtractedDocument:
    return ExtractedDocument(
        document_id="doc_1",
        tenant_id="t",
        doc_type=doc_type,
        header=DocumentHeader(
            document_id="doc_1",
            doc_type=doc_type,
            vendor_name=_pv(vendor) if vendor else None,
            grand_total=_pv(grand_total) if grand_total else None,
        ),
        line_items=lines or [],
        tax_lines=tax_lines or [],
        coverage=Coverage(pages_total=1, pages_examined=1, coverage_complete=True),
        page_count=1,
        extractor_version="test",
    )


def _line(num: int, desc: str, qty: str, price: str, total: str) -> LineItem:
    return LineItem(
        line_number=num,
        description=_pv(desc),
        quantity=_pv(qty),
        unit_price=_pv(price),
        line_total=_pv(total),
    )


class TestMergeHeader:
    def test_agreement_keeps_regex_value_and_boosts_confidence(self):
        regex = _doc(vendor="Acme")
        vlm = _doc(vendor="Acme")
        vlm.header.vendor_name = ProvenancedValue(
            value="Acme", raw="Acme", confidence=0.95,
        )
        result = merge_extractions(regex, vlm)
        assert result.disagreements == {}
        assert result.merged.header.vendor_name.value == "Acme"
        assert result.merged.header.vendor_name.confidence > 0.9

    def test_disagreement_keeps_regex_value_and_flags_field(self):
        regex = _doc(vendor="Acme", grand_total="1000.00")
        vlm = _doc(vendor="Acme", grand_total="1500.00")
        result = merge_extractions(regex, vlm)
        assert "grand_total" in result.disagreements
        assert "1000.00 vs 1500.00" in result.disagreements["grand_total"]
        assert result.merged.header.grand_total.value == "1000.00"
        assert result.merged.extraction_disagreements == {"grand_total": "1000.00 vs 1500.00"}

    def test_one_sided_field_kept_with_penalty(self):
        regex = _doc(vendor=None, grand_total="1000.00")
        vlm = _doc(vendor="VlmCo", grand_total="1000.00")
        result = merge_extractions(regex, vlm)
        assert result.disagreements == {}
        assert result.merged.header.vendor_name.value == "VlmCo"
        assert result.merged.header.vendor_name.confidence < 0.95

    def test_amounts_equal_across_locale_formats(self):
        regex = _doc(grand_total="1,000.50")
        vlm = _doc(grand_total="1000.50")
        result = merge_extractions(regex, vlm)
        assert result.disagreements == {}

    def test_missing_on_both_sides_stays_missing(self):
        regex = _doc(vendor=None)
        vlm = _doc(vendor=None)
        result = merge_extractions(regex, vlm)
        assert result.merged.header.vendor_name is None
        assert result.disagreements == {}

    def test_bank_details_fallback_to_vlm(self):
        regex = _doc()
        vlm = _doc()
        vlm.header.bank_details = {"account_number": "12345"}
        result = merge_extractions(regex, vlm)
        assert result.merged.header.bank_details == {"account_number": "12345"}


class TestMergeLineItems:
    def test_matching_lines_merged_by_number(self):
        regex = _doc(lines=[_line(1, "Widget A", "10", "100.00", "1000.00")])
        vlm = _doc(lines=[_line(1, "Widget A", "10", "100.00", "1000.00")])
        result = merge_extractions(regex, vlm)
        assert len(result.merged.line_items) == 1
        assert result.disagreements == {}

    def test_line_field_disagreement_flagged(self):
        regex = _doc(lines=[_line(1, "Widget A", "10", "100.00", "1000.00")])
        vlm = _doc(lines=[_line(1, "Widget A", "12", "100.00", "1200.00")])
        result = merge_extractions(regex, vlm)
        assert "line_items[1].quantity" in result.disagreements
        assert "line_items[1].line_total" in result.disagreements
        assert result.merged.line_items[0].quantity.value == "10"

    def test_fuzzy_match_by_description(self):
        regex = _doc(lines=[_line(1, "Widget A", "10", "100.00", "1000.00")])
        vlm = _doc(lines=[_line(3, "widget a", "10", "100.00", "1000.00")])
        result = merge_extractions(regex, vlm)
        assert len(result.merged.line_items) == 1
        assert result.merged.line_items[0].line_number == 1

    def test_vlm_only_lines_appended(self):
        regex = _doc(lines=[_line(1, "Widget A", "10", "100.00", "1000.00")])
        vlm = _doc(lines=[
            _line(1, "Widget A", "10", "100.00", "1000.00"),
            _line(2, "Widget B", "5", "50.00", "250.00"),
        ])
        result = merge_extractions(regex, vlm)
        assert len(result.merged.line_items) == 2
        assert result.merged.line_items[1].line_number == 2


class TestMergeCoverage:
    def test_complete_coverage_wins(self):
        regex = _doc()
        regex.coverage = Coverage(
            pages_total=3, pages_examined=1, coverage_complete=False,
        )
        vlm = _doc()
        vlm.coverage = Coverage(
            pages_total=3, pages_examined=3, coverage_complete=True,
        )
        result = merge_extractions(regex, vlm)
        assert result.merged.coverage.coverage_complete is True

    def test_narrative_report_carried_from_vlm(self):
        regex = _doc()
        vlm = _doc()
        vlm.narrative_report = "Summarised."
        result = merge_extractions(regex, vlm)
        assert result.merged.narrative_report == "Summarised."

    def test_extractor_version(self):
        result = merge_extractions(_doc(), _doc())
        assert result.merged.extractor_version == "dual_1.0.0"
