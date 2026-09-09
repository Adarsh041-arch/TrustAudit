from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from audit_v2.domain.models import DocumentType, ExtractedDocument, ProvenancedValue


# ─── Parser tests ──────────────────────────────────────────────────────────


class TestParseAmount:
    def test_en_us_format(self):
        from audit_v2.extraction.parser import parse_amount
        assert parse_amount("1,000.50", "en-US") == Decimal("1000.50")

    def test_de_de_format(self):
        from audit_v2.extraction.parser import parse_amount
        assert parse_amount("1.000,50", "de-DE") == Decimal("1000.50")

    def test_en_in_format(self):
        from audit_v2.extraction.parser import parse_amount
        assert parse_amount("1,00,000.50", "en-IN") == Decimal("100000.50")

    def test_accounting_negative(self):
        from audit_v2.extraction.parser import parse_amount
        assert parse_amount("(1,000.50)", "en-US") == Decimal("-1000.50")

    def test_fr_fr_space_format(self):
        from audit_v2.extraction.parser import parse_amount
        assert parse_amount("1 000,50", "fr-FR") == Decimal("1000.50")

    def test_no_separator(self):
        from audit_v2.extraction.parser import parse_amount
        assert parse_amount("1000.50", "en-US") == Decimal("1000.50")

    def test_integer_amount(self):
        from audit_v2.extraction.parser import parse_amount
        assert parse_amount("1000", "en-US") == Decimal("1000")

    def test_currency_prefix_stripped(self):
        from audit_v2.extraction.parser import parse_amount
        assert parse_amount("$1,000.50", "en-US") == Decimal("1000.50")
        assert parse_amount("Rs. 1,000.50", "en-IN") == Decimal("1000.50")
        assert parse_amount("INR 1,000.50", "en-IN") == Decimal("1000.50")

    def test_ambiguous_requires_review(self):
        from audit_v2.extraction.parser import parse_amount
        result = parse_amount("1.000", None)
        assert result is None


class TestParseDate:
    def test_dd_mm_yyyy(self):
        from audit_v2.extraction.parser import parse_date
        assert parse_date("25/07/2026") == date(2026, 7, 25)

    def test_dd_mm_yy(self):
        from audit_v2.extraction.parser import parse_date
        assert parse_date("25-07-26") == date(2026, 7, 25)

    def test_yyyy_mm_dd(self):
        from audit_v2.extraction.parser import parse_date
        assert parse_date("2026-07-25") == date(2026, 7, 25)

    def test_dd_month_yyyy(self):
        from audit_v2.extraction.parser import parse_date
        assert parse_date("25 Jul 2026") == date(2026, 7, 25)

    def test_dd_month_yyyy_full(self):
        from audit_v2.extraction.parser import parse_date
        assert parse_date("25 July 2026") == date(2026, 7, 25)

    def test_invalid_date_returns_none(self):
        from audit_v2.extraction.parser import parse_date
        assert parse_date("not-a-date") is None


class TestValidateGstin:
    def test_valid_gstin(self):
        from audit_v2.extraction.parser import validate_gstin
        assert validate_gstin("27AAAPL1234C1Z2")

    def test_invalid_gstin_too_short(self):
        from audit_v2.extraction.parser import validate_gstin
        assert not validate_gstin("27AAAPL1")

    def test_invalid_gstin_bad_chars(self):
        from audit_v2.extraction.parser import validate_gstin
        assert not validate_gstin("27AAAPL1234C1Z@")

    def test_empty_gstin(self):
        from audit_v2.extraction.parser import validate_gstin
        assert not validate_gstin("")


class TestValidateHsn:
    def test_valid_4_digit_hsn(self):
        from audit_v2.extraction.parser import validate_hsn
        assert validate_hsn("8471")

    def test_valid_8_digit_hsn(self):
        from audit_v2.extraction.parser import validate_hsn
        assert validate_hsn("84713000")

    def test_invalid_hsn(self):
        from audit_v2.extraction.parser import validate_hsn
        assert not validate_hsn("12")

    def test_empty_hsn(self):
        from audit_v2.extraction.parser import validate_hsn
        assert not validate_hsn("")


class TestParsePoReference:
    def test_po_prefix(self):
        from audit_v2.extraction.parser import extract_po_reference
        assert extract_po_reference("PO-2026-0042") == "PO-2026-0042"

    def test_po_with_dot(self):
        from audit_v2.extraction.parser import extract_po_reference
        assert extract_po_reference("P.O. 2026/042") == "P.O. 2026/042"

    def test_po_number_only(self):
        from audit_v2.extraction.parser import extract_po_reference
        assert extract_po_reference("Purchase Order #2026042") == "2026042"

    def test_no_po_reference(self):
        from audit_v2.extraction.parser import extract_po_reference
        assert extract_po_reference("This is an invoice without PO") is None

    def test_po_label_without_value_is_not_a_reference(self):
        from audit_v2.extraction.parser import extract_po_reference
        assert extract_po_reference("PO Reference") is None


class TestValidateIfsc:
    def test_valid_ifsc(self):
        from audit_v2.extraction.parser import validate_ifsc
        assert validate_ifsc("SBIN0001234")

    def test_invalid_ifsc_too_short(self):
        from audit_v2.extraction.parser import validate_ifsc
        assert not validate_ifsc("SBI1234")

    def test_invalid_ifsc_bad_prefix(self):
        from audit_v2.extraction.parser import validate_ifsc
        assert not validate_ifsc("12BN0001234")


class TestNormalizeLocale:
    def test_en_us(self):
        from audit_v2.extraction.parser import normalize_locale
        assert normalize_locale("1,000.50", "en-US") == "1000.50"

    def test_de_de(self):
        from audit_v2.extraction.parser import normalize_locale
        assert normalize_locale("1.000,50", "de-DE") == "1000.50"

    def test_en_in(self):
        from audit_v2.extraction.parser import normalize_locale
        assert normalize_locale("1,00,000.50", "en-IN") == "100000.50"

    def test_none_locale_returns_raw(self):
        from audit_v2.extraction.parser import normalize_locale
        assert normalize_locale("1000.50", None) == "1000.50"


# ─── BaseExtractor tests ───────────────────────────────────────────────────


class TestBaseExtractor:
    def test_extract_raises_not_implemented(self):
        from audit_v2.extraction.base import BaseExtractor
        from audit_v2.domain.models import DocumentHeader
        class MinimalExtractor(BaseExtractor):
            def extract(self, data: bytes, mime_type: str) -> ExtractedDocument:
                raise NotImplementedError
            def extract_header(self) -> DocumentHeader:
                return super().extract_header()
        inst = MinimalExtractor()
        with pytest.raises(NotImplementedError):
            inst.extract_header()

    def test_subclass_with_all_methods(self):
        from audit_v2.extraction.base import BaseExtractor
        from audit_v2.domain.models import DocumentType, Coverage

        class FullExtractor(BaseExtractor):
            def extract(self, data: bytes, mime_type: str) -> ExtractedDocument:
                return ExtractedDocument(
                    document_id="test",
                    tenant_id="t",
                    doc_type=DocumentType.INVOICE,
                    header=self.extract_header(),
                    line_items=self.extract_line_items(),
                    tax_lines=self.extract_tax_lines(),
                    coverage=self.get_coverage(),
                    page_count=1,
                    extractor_version="1.0.0",
                )
            def extract_header(self):
                from audit_v2.domain.models import DocumentHeader
                return DocumentHeader(document_id="test", doc_type=DocumentType.INVOICE)
            def extract_line_items(self):
                return []
            def extract_tax_lines(self):
                return []
            def get_coverage(self):
                return Coverage(pages_total=1, pages_examined=1, pages_unreadable=[], coverage_complete=True)

        ext = FullExtractor()
        result = ext.extract(b"data", "application/pdf")
        assert isinstance(result, ExtractedDocument)
        assert result.doc_type == DocumentType.INVOICE
        assert result.page_count == 1


# ─── Invoice extractor tests ───────────────────────────────────────────────


SAMPLE_INVOICE_TEXT = """Tax Invoice
Invoice No: INV-2026-0042
Date: 25/07/2026
PO Reference: PO-2026-0015

Seller: Acme Corp Pvt Ltd
GSTIN: 27AAAPL1234C1Z2
Address: 123 Industrial Area, Mumbai - 400001

Buyer: Tech Solutions Inc
GSTIN: 29AABCT1234D1Z5

| # | Description          | HSN    | Qty | Rate    | Amount   |
|---|----------------------|--------|-----|---------|----------|
| 1 | Widget A             | 8471   | 5   | 1,000.00| 5,000.00 |
| 2 | Widget B             | 8471   | 10  | 800.00  | 8,000.00 |

Taxable Value: 13,000.00

HSN 8471 @ 18% GST
  CGST (9%):  1,170.00
  SGST (9%):  1,170.00

Total Tax: 2,340.00

Grand Total: 15,340.00

Amount in words: Rupees Fifteen Thousand Three Hundred Forty Only

Bank Details:
Account No: 1234567890
IFSC: SBIN0001234
"""


class TestInvoiceExtractor:
    def test_extract_header_fields(self):
        from audit_v2.extraction.invoice_extractor import InvoiceExtractor
        ext = InvoiceExtractor()
        header = ext._extract_header_from_text(SAMPLE_INVOICE_TEXT)
        assert header.document_id == "INV-2026-0042"
        assert header.vendor_name is not None
        assert header.vendor_name.value == "Acme Corp Pvt Ltd"
        assert header.vendor_gstin is not None
        assert header.vendor_gstin.value == "27AAAPL1234C1Z2"
        assert header.invoice_date is not None
        assert header.invoice_date.value == "2026-07-25"
        assert header.po_reference is not None
        assert header.po_reference.value == "PO-2026-0015"
        assert header.buyer_name is not None
        assert header.buyer_name.value == "Tech Solutions Inc"

    def test_extract_line_items(self):
        from audit_v2.extraction.invoice_extractor import InvoiceExtractor
        ext = InvoiceExtractor()
        items = ext._extract_line_items_from_text(SAMPLE_INVOICE_TEXT)
        assert len(items) == 2
        assert items[0].line_number == 1
        assert items[0].description.value == "Widget A"
        assert items[0].quantity.decimal_value == Decimal("5")
        assert items[0].unit_price.decimal_value == Decimal("1000.00")
        assert items[0].line_total.decimal_value == Decimal("5000.00")
        assert items[0].hsn_sac is not None
        assert items[0].hsn_sac.value == "8471"
        assert items[1].line_number == 2
        assert items[1].description.value == "Widget B"
        assert items[1].quantity.decimal_value == Decimal("10")

    def test_extract_tax_lines(self):
        from audit_v2.extraction.invoice_extractor import InvoiceExtractor
        ext = InvoiceExtractor()
        tax_lines = ext._extract_tax_lines_from_text(SAMPLE_INVOICE_TEXT)
        assert len(tax_lines) >= 1
        cgst = [t for t in tax_lines if "CGST" in t.description.value]
        sgst = [t for t in tax_lines if "SGST" in t.description.value]
        assert len(cgst) >= 1
        assert len(sgst) >= 1

    def test_extract_full_document(self):
        from audit_v2.extraction.invoice_extractor import InvoiceExtractor
        ext = InvoiceExtractor()
        doc = ext.extract(SAMPLE_INVOICE_TEXT.encode(), "text/plain")
        assert isinstance(doc, ExtractedDocument)
        assert doc.doc_type.value == "invoice"
        assert len(doc.line_items) == 2
        assert len(doc.tax_lines) >= 2
        assert doc.page_count == 1
        assert doc.extractor_version != ""

    def test_provenance_on_all_fields(self):
        from audit_v2.extraction.invoice_extractor import InvoiceExtractor
        ext = InvoiceExtractor()
        doc = ext.extract(SAMPLE_INVOICE_TEXT.encode(), "text/plain")
        all_pvs: list[ProvenancedValue] = []
        if doc.header.vendor_name:
            all_pvs.append(doc.header.vendor_name)
        if doc.header.vendor_gstin:
            all_pvs.append(doc.header.vendor_gstin)
        if doc.header.invoice_date:
            all_pvs.append(doc.header.invoice_date)
        if doc.header.po_reference:
            all_pvs.append(doc.header.po_reference)
        if doc.header.grand_total:
            all_pvs.append(doc.header.grand_total)
        for li in doc.line_items:
            all_pvs.extend([li.description, li.quantity, li.unit_price, li.line_total])
            if li.hsn_sac:
                all_pvs.append(li.hsn_sac)
        for pv in all_pvs:
            assert pv.value != "", f"Empty value in {pv}"
            assert pv.raw != "", f"Empty raw in {pv}"
            assert pv.page >= 1, f"Missing page in {pv}"

    def test_extract_raises_on_empty_data(self):
        from audit_v2.extraction.invoice_extractor import InvoiceExtractor
        ext = InvoiceExtractor()
        with pytest.raises(ValueError):
            ext.extract(b"", "application/pdf")


# ─── Text extractor tests ──────────────────────────────────────────────────


class TestTextExtractor:
    def test_extract_blocks_from_pdf(self):
        from audit_v2.extraction.text_extractor import TextExtractor
        ext = TextExtractor()
        pdf_path = Path(__file__).resolve().parent.parent / "sample_docs" / "INV-2026-0715_NewTech_Solutions.pdf"
        if not pdf_path.exists():
            pytest.skip("Sample PDF not found")
        data = pdf_path.read_bytes()
        blocks = ext.extract_text_blocks(data)
        assert len(blocks) > 0
        for block in blocks:
            assert "text" in block
            assert "page" in block
            assert block["page"] >= 1

    def test_extract_blocks_empty_pdf(self):
        from audit_v2.extraction.text_extractor import TextExtractor
        ext = TextExtractor()
        dummy_pdf = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\nxref\n"
            b"0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
            b"trailer<</Size 3/Root 1 0 R>>\nstartxref\n120\n%%EOF"
        )
        blocks = ext.extract_text_blocks(dummy_pdf)
        assert blocks == []

    def test_text_layer_detection(self):
        from audit_v2.extraction.text_extractor import TextExtractor
        ext = TextExtractor()
        pdf_path = Path(__file__).resolve().parent.parent / "sample_docs" / "INV-2026-0715_NewTech_Solutions.pdf"
        if not pdf_path.exists():
            pytest.skip("Sample PDF not found")
        data = pdf_path.read_bytes()
        assert ext.has_text_layer(data) is True


# ─── Confidence tests ──────────────────────────────────────────────────────


class TestConfidence:
    def test_full_agreement_gives_high_confidence(self):
        from audit_v2.extraction.confidence import compute_field_confidence
        conf = compute_field_confidence(
            field_name="vendor_name",
            text_layer_confidence=0.95,
            vlm_confidence=0.94,
            agreement=1.0,
        )
        assert conf >= 0.90

    def test_disagreement_reduces_confidence(self):
        from audit_v2.extraction.confidence import compute_field_confidence
        conf = compute_field_confidence(
            field_name="line_total",
            text_layer_confidence=0.98,
            vlm_confidence=0.99,
            agreement=0.0,
        )
        assert conf < 0.50

    def test_text_layer_only_medium_confidence(self):
        from audit_v2.extraction.confidence import compute_field_confidence
        conf = compute_field_confidence("gstin", 0.85, None, None)
        assert conf == 0.85

    def test_vlm_only_lower_confidence(self):
        from audit_v2.extraction.confidence import compute_field_confidence
        conf = compute_field_confidence("description", None, 0.80, None)
        assert conf < 0.80

    def test_agreement_score_identical(self):
        from audit_v2.extraction.confidence import agreement_score
        a = {"vendor_name": "Acme Corp", "inv_date": "2026-07-25"}
        b = {"vendor_name": "Acme Corp", "inv_date": "2026-07-25"}
        assert agreement_score(a, b) == 1.0

    def test_agreement_score_partial(self):
        from audit_v2.extraction.confidence import agreement_score
        a = {"vendor_name": "Acme Corp", "inv_date": "2026-07-25", "total": "1000"}
        b = {"vendor_name": "Acme Corp", "inv_date": "2026-07-26", "total": "1000"}
        score = agreement_score(a, b)
        assert 0.3 < score < 0.7
