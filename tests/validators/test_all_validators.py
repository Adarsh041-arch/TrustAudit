"""Direct unit tests for every validator function.

PHASES_V2 §4 Phase 6 requires >=95% branch coverage on the validator package:
these are pure functions, so there is no excuse for less.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from audit_v2.domain.catalog_loader import load_catalog
from audit_v2.domain.models import (
    CheckContext,
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
    FindingStatus,
    LineItem,
    ProvenancedValue,
    TaxLine,
)
from audit_v2.domain.validators import (
    arithmetic,
    duplicate,
    format_completeness,
    reference_integrity,
    rollforward,
    sequence,
    temporal,
    threshold,
)

CATALOG = {c.check_id: c for c in load_catalog().checks}


def pv(value: str, raw: str | None = None, currency: str | None = None) -> ProvenancedValue:
    return ProvenancedValue(value=value, raw=raw or value, page=1, currency=currency)


def line(n: int, qty: str, price: str, total: str, hsn: str | None = "8471") -> LineItem:
    return LineItem(
        line_number=n,
        description=pv(f"Item {n}"),
        quantity=pv(qty),
        unit_price=pv(price),
        line_total=pv(total),
        hsn_sac=pv(hsn) if hsn else None,
    )


def tax(rate: str, cgst: str, sgst: str, total: str, taxable: str = "1000.00") -> TaxLine:
    return TaxLine(
        line_number=1, description=pv("GST"), taxable_value=pv(taxable),
        rate=pv(rate), cgst=pv(cgst), sgst=pv(sgst), total_tax=pv(total),
    )


def doc(
    doc_type: DocumentType = DocumentType.INVOICE,
    lines: list[LineItem] | None = None,
    taxes: list[TaxLine] | None = None,
    **header_kwargs,
) -> ExtractedDocument:
    header = DocumentHeader(document_id="d", doc_type=doc_type, **header_kwargs)
    return ExtractedDocument(
        document_id="d", tenant_id="t", doc_type=doc_type, header=header,
        line_items=lines or [], tax_lines=taxes or [],
        coverage=Coverage(pages_total=1, pages_examined=1, coverage_complete=True),
        page_count=1, extractor_version="2.1.0",
    )


def ctx(document: ExtractedDocument, check_id: str, **kw) -> CheckContext:
    return CheckContext(document=document, check_entry=CATALOG[check_id], **kw)


class TestArithmetic:
    def test_line_total_passes_when_consistent(self):
        d = doc(lines=[line(1, "5", "30.00", "150.00")])
        assert arithmetic.check_line_total(
            ctx(d, "CHK-ARITH-LINE-001")).status == FindingStatus.PASS

    def test_line_total_fails_when_overstated(self):
        d = doc(lines=[line(1, "5", "30.00", "200.00")])
        r = arithmetic.check_line_total(ctx(d, "CHK-ARITH-LINE-001"))
        assert r.status == FindingStatus.FAIL
        assert r.expected == "150.00"
        assert r.actual == "200.00"
        assert r.evidence

    def test_line_total_zero_decimal_currency(self):
        d = doc(lines=[line(1, "3", "1000", "3000")])
        r = arithmetic.check_line_total(
            ctx(d, "CHK-ARITH-LINE-001", currency_exponent=Decimal("1")))
        assert r.status == FindingStatus.PASS

    def test_subtotal_skips_without_line_items(self):
        r = arithmetic.check_subtotal_tieout(ctx(doc(), "CHK-ARITH-SUBTOTAL-001"))
        assert r.status == FindingStatus.SKIPPED

    def test_subtotal_skips_without_subtotal_field(self):
        d = doc(lines=[line(1, "1", "10.00", "10.00")])
        r = arithmetic.check_subtotal_tieout(ctx(d, "CHK-ARITH-SUBTOTAL-001"))
        assert r.status == FindingStatus.SKIPPED

    def test_subtotal_passes_and_fails(self):
        good = doc(lines=[line(1, "1", "10.00", "10.00")], subtotal=pv("10.00"))
        assert arithmetic.check_subtotal_tieout(
            ctx(good, "CHK-ARITH-SUBTOTAL-001")).status == FindingStatus.PASS
        bad = doc(lines=[line(1, "1", "10.00", "10.00")], subtotal=pv("99.00"))
        assert arithmetic.check_subtotal_tieout(
            ctx(bad, "CHK-ARITH-SUBTOTAL-001")).status == FindingStatus.FAIL

    def test_tax_rate_skips_without_tax_lines(self):
        r = arithmetic.check_tax_rate(ctx(doc(), "CHK-ARITH-TAX-001"))
        assert r.status == FindingStatus.SKIPPED

    @pytest.mark.parametrize("rate", ["0", "5", "9", "12", "18", "28"])
    def test_tax_rate_accepts_valid_slabs(self, rate):
        d = doc(taxes=[tax(rate, "50.00", "50.00", "100.00")])
        assert arithmetic.check_tax_rate(
            ctx(d, "CHK-ARITH-TAX-001")).status == FindingStatus.PASS

    def test_tax_rate_rejects_invalid_slab(self):
        d = doc(taxes=[tax("17", "50.00", "50.00", "100.00")])
        r = arithmetic.check_tax_rate(ctx(d, "CHK-ARITH-TAX-001"))
        assert r.status == FindingStatus.FAIL

    def test_tax_calculation_component_mismatch_fails(self):
        d = doc(taxes=[tax("18", "50.00", "50.00", "999.00")])
        assert arithmetic.check_tax_calculation(
            ctx(d, "CHK-ARITH-TAX-002")).status == FindingStatus.FAIL

    def test_tax_calculation_recomputes_from_taxable_base(self):
        good = doc(taxes=[tax("18", "90.00", "90.00", "180.00", taxable="1000.00")])
        assert arithmetic.check_tax_calculation(
            ctx(good, "CHK-ARITH-TAX-002")).status == FindingStatus.PASS
        bad = doc(taxes=[tax("18", "50.00", "50.00", "100.00", taxable="1000.00")])
        assert arithmetic.check_tax_calculation(
            ctx(bad, "CHK-ARITH-TAX-002")).status == FindingStatus.FAIL

    def test_tax_calculation_skips_recompute_when_base_missing(self):
        d = doc(taxes=[tax("18", "50.00", "50.00", "100.00", taxable="0")])
        assert arithmetic.check_tax_calculation(
            ctx(d, "CHK-ARITH-TAX-002")).status == FindingStatus.PASS

    def test_discount_cap_skips_without_percentage(self):
        assert arithmetic.check_discount_cap(
            ctx(doc(), "CHK-ARITH-DISCOUNT-001")).status == FindingStatus.SKIPPED

    def test_discount_cap_fails_above_default_max(self):
        d = doc(discount_percentage=pv("35"), subtotal=pv("100000.00"))
        r = arithmetic.check_discount_cap(ctx(d, "CHK-ARITH-DISCOUNT-001"))
        assert r.status == FindingStatus.FAIL, "large subtotal must not mask an excess discount"

    def test_discount_cap_passes_within_max(self):
        d = doc(discount_percentage=pv("10"), subtotal=pv("100000.00"))
        assert arithmetic.check_discount_cap(
            ctx(d, "CHK-ARITH-DISCOUNT-001")).status == FindingStatus.PASS

    def test_discount_cap_honours_tenant_override(self):
        d = doc(discount_percentage=pv("35"), subtotal=pv("1000.00"))
        c = ctx(d, "CHK-ARITH-DISCOUNT-001", tenant_tolerances={"MAX_DISCOUNT_PCT": "50"})
        assert arithmetic.check_discount_cap(c).status == FindingStatus.PASS

    def test_grand_total_skips_when_inputs_absent(self):
        assert arithmetic.check_grand_total(
            ctx(doc(), "CHK-ARITH-GRAND-001")).status == FindingStatus.SKIPPED
        d = doc(grand_total=pv("100.00"))
        assert arithmetic.check_grand_total(
            ctx(d, "CHK-ARITH-GRAND-001")).status == FindingStatus.SKIPPED

    def test_grand_total_passes_with_tax_and_discount(self):
        d = doc(
            taxes=[tax("18", "90.00", "90.00", "180.00")],
            subtotal=pv("1000.00"), discount_amount=pv("80.00"),
            grand_total=pv("1100.00"),
        )
        assert arithmetic.check_grand_total(
            ctx(d, "CHK-ARITH-GRAND-001")).status == FindingStatus.PASS

    def test_grand_total_fails_when_overstated(self):
        d = doc(subtotal=pv("1000.00"), grand_total=pv("5000.00"))
        assert arithmetic.check_grand_total(
            ctx(d, "CHK-ARITH-GRAND-001")).status == FindingStatus.FAIL

    def test_rounding_accumulation(self):
        empty = arithmetic.check_rounding_accumulation(
            ctx(doc(), "CHK-ARITH-ROUNDING-001"))
        assert empty.status == FindingStatus.PASS
        good = doc(lines=[line(1, "2", "10.00", "20.00")])
        assert arithmetic.check_rounding_accumulation(
            ctx(good, "CHK-ARITH-ROUNDING-001")).status == FindingStatus.PASS
        bad = doc(lines=[line(1, "2", "10.00", "500.00")])
        assert arithmetic.check_rounding_accumulation(
            ctx(bad, "CHK-ARITH-ROUNDING-001")).status == FindingStatus.FAIL


class TestRollForward:
    def test_skips_when_any_field_missing(self):
        r = rollforward.check_balance_roll_forward(ctx(doc(), "CHK-RFWD-BALANCE-001"))
        assert r.status == FindingStatus.SKIPPED
        assert "opening_balance" in r.message

    def test_passes_when_balance_rolls(self):
        d = doc(opening_balance=pv("100.00"), receipts=pv("50.00"),
                payments=pv("30.00"), closing_balance=pv("120.00"))
        assert rollforward.check_balance_roll_forward(
            ctx(d, "CHK-RFWD-BALANCE-001")).status == FindingStatus.PASS

    def test_fails_when_balance_does_not_roll(self):
        d = doc(opening_balance=pv("100.00"), receipts=pv("50.00"),
                payments=pv("30.00"), closing_balance=pv("999.00"))
        assert rollforward.check_balance_roll_forward(
            ctx(d, "CHK-RFWD-BALANCE-001")).status == FindingStatus.FAIL

    def test_non_numeric_field_is_treated_as_missing(self):
        d = doc(opening_balance=pv("N/A"), receipts=pv("50.00"),
                payments=pv("30.00"), closing_balance=pv("120.00"))
        assert rollforward.check_balance_roll_forward(
            ctx(d, "CHK-RFWD-BALANCE-001")).status == FindingStatus.SKIPPED


class TestSequence:
    @pytest.mark.parametrize("fn,check_id", [
        (sequence.check_invoice_sequence, "CHK-SEQ-INVNUM-001"),
        (sequence.check_po_sequence, "CHK-SEQ-PONUM-001"),
        (sequence.check_challan_sequence, "CHK-SEQ-CHALLAN-001"),
    ])
    def test_corpus_checks_skip_never_pass(self, fn, check_id):
        """An unimplemented corpus check must SKIP, never report compliant."""
        r = fn(ctx(doc(), check_id))
        assert r.status == FindingStatus.SKIPPED


class TestThreshold:
    def test_line_threshold_passes_and_skips(self):
        assert threshold.check_line_threshold(
            ctx(doc(), "CHK-THRESHOLD-LINE-001")).status == FindingStatus.PASS
        d = doc(lines=[line(1, "1", "10.00", "10.00")])
        assert threshold.check_line_threshold(
            ctx(d, "CHK-THRESHOLD-LINE-001")).status == FindingStatus.SKIPPED

    def test_line_threshold_fails_when_line_exceeds_total(self):
        d = doc(lines=[line(1, "1", "500.00", "500.00")], grand_total=pv("100.00"))
        assert threshold.check_line_threshold(
            ctx(d, "CHK-THRESHOLD-LINE-001")).status == FindingStatus.FAIL

    def test_discount_threshold_range(self):
        assert threshold.check_discount_threshold(
            ctx(doc(), "CHK-THRESHOLD-DISC-001")).status == FindingStatus.SKIPPED
        assert threshold.check_discount_threshold(
            ctx(doc(discount_percentage=pv("-5")),
                "CHK-THRESHOLD-DISC-001")).status == FindingStatus.FAIL
        assert threshold.check_discount_threshold(
            ctx(doc(discount_percentage=pv("150")),
                "CHK-THRESHOLD-DISC-001")).status == FindingStatus.FAIL
        assert threshold.check_discount_threshold(
            ctx(doc(discount_percentage=pv("15")),
                "CHK-THRESHOLD-DISC-001")).status == FindingStatus.PASS

    def test_tax_rate_threshold(self):
        good = doc(taxes=[tax("9", "50.00", "50.00", "100.00")])
        assert threshold.check_tax_rate_threshold(
            ctx(good, "CHK-THRESHOLD-TAXRATE-001")).status == FindingStatus.PASS
        bad = doc(taxes=[tax("17", "50.00", "50.00", "100.00")])
        assert threshold.check_tax_rate_threshold(
            ctx(bad, "CHK-THRESHOLD-TAXRATE-001")).status == FindingStatus.FAIL


class TestTemporal:
    def test_invoice_date_ordering(self):
        assert temporal.check_invoice_date(
            ctx(doc(), "CHK-TEMP-INVDATE-001")).status == FindingStatus.SKIPPED
        assert temporal.check_invoice_date(
            ctx(doc(invoice_date=pv("2026-07-15")),
                "CHK-TEMP-INVDATE-001")).status == FindingStatus.SKIPPED
        ok = doc(invoice_date=pv("2026-07-15"), received_date=pv("2026-07-20"))
        assert temporal.check_invoice_date(
            ctx(ok, "CHK-TEMP-INVDATE-001")).status == FindingStatus.PASS
        bad = doc(invoice_date=pv("2026-07-25"), received_date=pv("2026-07-20"))
        assert temporal.check_invoice_date(
            ctx(bad, "CHK-TEMP-INVDATE-001")).status == FindingStatus.FAIL

    def test_po_date_ordering(self):
        assert temporal.check_po_date(
            ctx(doc(), "CHK-TEMP-PODATE-001")).status == FindingStatus.SKIPPED
        assert temporal.check_po_date(
            ctx(doc(order_date=pv("2026-07-01")),
                "CHK-TEMP-PODATE-001")).status == FindingStatus.SKIPPED
        ok = doc(order_date=pv("2026-07-01"), invoice_date=pv("2026-07-15"))
        assert temporal.check_po_date(
            ctx(ok, "CHK-TEMP-PODATE-001")).status == FindingStatus.PASS
        bad = doc(order_date=pv("2026-07-20"), invoice_date=pv("2026-07-15"))
        assert temporal.check_po_date(
            ctx(bad, "CHK-TEMP-PODATE-001")).status == FindingStatus.FAIL

    def test_delivery_date_ordering(self):
        assert temporal.check_delivery_date(
            ctx(doc(), "CHK-TEMP-DELIVERY-001")).status == FindingStatus.SKIPPED
        assert temporal.check_delivery_date(
            ctx(doc(delivery_date=pv("2026-07-10")),
                "CHK-TEMP-DELIVERY-001")).status == FindingStatus.SKIPPED
        ok = doc(delivery_date=pv("2026-07-10"), grn_date=pv("2026-07-12"))
        assert temporal.check_delivery_date(
            ctx(ok, "CHK-TEMP-DELIVERY-001")).status == FindingStatus.PASS
        bad = doc(delivery_date=pv("2026-07-20"), grn_date=pv("2026-07-12"))
        assert temporal.check_delivery_date(
            ctx(bad, "CHK-TEMP-DELIVERY-001")).status == FindingStatus.FAIL

    def test_expiry_date(self):
        assert temporal.check_expiry_date(
            ctx(doc(), "CHK-TEMP-EXPIRY-001")).status == FindingStatus.SKIPPED
        future = (date.today() + timedelta(days=30)).isoformat()
        assert temporal.check_expiry_date(
            ctx(doc(expiry_date=pv(future)),
                "CHK-TEMP-EXPIRY-001")).status == FindingStatus.PASS
        past = (date.today() - timedelta(days=30)).isoformat()
        assert temporal.check_expiry_date(
            ctx(doc(expiry_date=pv(past)),
                "CHK-TEMP-EXPIRY-001")).status == FindingStatus.FAIL

    @pytest.mark.parametrize("raw", ["15-Jul-2026", "15/07/2026", "2026-07-15"])
    def test_accepted_date_formats(self, raw):
        d = doc(expiry_date=pv(raw))
        assert temporal.check_expiry_date(
            ctx(d, "CHK-TEMP-EXPIRY-001")).status != FindingStatus.SKIPPED

    def test_unparseable_date_is_skipped_not_crashed(self):
        d = doc(expiry_date=pv("not-a-date"))
        assert temporal.check_expiry_date(
            ctx(d, "CHK-TEMP-EXPIRY-001")).status == FindingStatus.SKIPPED


class TestReferenceIntegrity:
    def test_po_reference_presence(self):
        assert reference_integrity.check_po_reference(
            ctx(doc(), "CHK-REF-PO-001")).status == FindingStatus.FAIL
        d = doc(po_reference=pv("PO-2026-001"))
        assert reference_integrity.check_po_reference(
            ctx(d, "CHK-REF-PO-001")).status == FindingStatus.PASS

    def test_gstin_format(self):
        assert reference_integrity.check_gstin_format(
            ctx(doc(), "CHK-REF-GST-001")).status == FindingStatus.FAIL
        good = doc(vendor_gstin=pv("27AAGCN1234H1Z1"))
        assert reference_integrity.check_gstin_format(
            ctx(good, "CHK-REF-GST-001")).status == FindingStatus.PASS
        bad = doc(vendor_gstin=pv("NOTAGSTIN"))
        assert reference_integrity.check_gstin_format(
            ctx(bad, "CHK-REF-GST-001")).status == FindingStatus.FAIL

    @pytest.mark.parametrize("hsn", ["8471", "847130", "84713010"])
    def test_hsn_accepts_4_6_and_8_digits(self, hsn):
        """4-digit HSN headings are legal under the turnover-slab rules."""
        d = doc(lines=[line(1, "1", "10.00", "10.00", hsn=hsn)])
        assert reference_integrity.check_hsn_code(
            ctx(d, "CHK-REF-HSN-001")).status == FindingStatus.PASS

    @pytest.mark.parametrize("hsn", ["84", "847", "8471301099", "ABCD"])
    def test_hsn_rejects_invalid(self, hsn):
        d = doc(lines=[line(1, "1", "10.00", "10.00", hsn=hsn)])
        assert reference_integrity.check_hsn_code(
            ctx(d, "CHK-REF-HSN-001")).status == FindingStatus.FAIL

    def test_hsn_missing_fails(self):
        d = doc(lines=[line(1, "1", "10.00", "10.00", hsn=None)])
        assert reference_integrity.check_hsn_code(
            ctx(d, "CHK-REF-HSN-001")).status == FindingStatus.FAIL

    def test_bank_details(self):
        assert reference_integrity.check_bank_details(
            ctx(doc(), "CHK-REF-BANK-001")).status == FindingStatus.FAIL
        partial = doc(bank_details={"account_number": "123456789"})
        r = reference_integrity.check_bank_details(ctx(partial, "CHK-REF-BANK-001"))
        assert r.status == FindingStatus.FAIL
        assert "ifsc" in r.message
        full = doc(bank_details={"account_number": "123456789", "ifsc": "KKBK0001234"})
        assert reference_integrity.check_bank_details(
            ctx(full, "CHK-REF-BANK-001")).status == FindingStatus.PASS

    @pytest.mark.parametrize("fn,check_id", [
        (reference_integrity.check_quantity_po, "CHK-REF-QTY-001"),
        (reference_integrity.check_quantity_dc, "CHK-REF-QTY-002"),
    ])
    def test_cross_document_checks_skip(self, fn, check_id):
        assert fn(ctx(doc(), check_id)).status == FindingStatus.SKIPPED


class TestFormatCompleteness:
    def test_mandatory_fields_invoice(self):
        r = format_completeness.check_mandatory_fields(
            ctx(doc(), "CHK-FORMAT-MANDATORY-001"))
        assert r.status == FindingStatus.FAIL
        complete = doc(
            vendor_name=pv("Acme"), vendor_gstin=pv("27AAGCN1234H1Z1"),
            invoice_date=pv("2026-07-15"), grand_total=pv("100.00"),
        )
        assert format_completeness.check_mandatory_fields(
            ctx(complete, "CHK-FORMAT-MANDATORY-001")).status == FindingStatus.PASS

    @pytest.mark.parametrize("doc_type,fields", [
        (DocumentType.PURCHASE_ORDER, {"vendor_name": pv("A"), "order_date": pv("2026-07-01")}),
        (DocumentType.DELIVERY_CHALLAN,
         {"vendor_name": pv("A"), "delivery_date": pv("2026-07-01")}),
        (DocumentType.GOODS_RECEIPT_NOTE,
         {"vendor_name": pv("A"), "grn_date": pv("2026-07-01")}),
    ])
    def test_mandatory_fields_other_doc_types(self, doc_type, fields):
        d = doc(doc_type=doc_type, **fields)
        assert format_completeness.check_mandatory_fields(
            ctx(d, "CHK-FORMAT-MANDATORY-001")).status == FindingStatus.PASS

    def test_line_item_fields_present(self):
        d = doc(lines=[line(1, "1", "10.00", "10.00")])
        assert format_completeness.check_line_item_fields(
            ctx(d, "CHK-FORMAT-MANDATORY-002")).status == FindingStatus.PASS

    @pytest.mark.parametrize("field", ["description", "quantity", "unit_price", "line_total"])
    def test_line_item_missing_field_fails(self, field):
        li = line(1, "1", "10.00", "10.00")
        setattr(li, field, pv("", raw=""))
        d = doc(lines=[li])
        r = format_completeness.check_line_item_fields(
            ctx(d, "CHK-FORMAT-MANDATORY-002"))
        assert r.status == FindingStatus.FAIL
        assert field in r.message

    def test_tax_breakdown(self):
        d = doc(taxes=[tax("18", "90.00", "90.00", "180.00")])
        assert format_completeness.check_tax_breakdown(
            ctx(d, "CHK-FORMAT-TAXBREAKDOWN-001")).status == FindingStatus.PASS
        t = tax("18", "90.00", "90.00", "180.00")
        t.rate = pv("", raw="")
        bad = doc(taxes=[t])
        r = format_completeness.check_tax_breakdown(
            ctx(bad, "CHK-FORMAT-TAXBREAKDOWN-001"))
        assert r.status == FindingStatus.FAIL
        assert "rate" in r.message

    def test_currency_consistency(self):
        consistent = doc(lines=[
            LineItem(line_number=1, description=pv("A"),
                     quantity=pv("1"), unit_price=pv("10.00", currency="INR"),
                     line_total=pv("10.00", currency="INR")),
        ])
        assert format_completeness.check_currency_format(
            ctx(consistent, "CHK-FORMAT-CURRENCY-001")).status == FindingStatus.PASS
        mixed = doc(lines=[
            LineItem(line_number=1, description=pv("A"),
                     quantity=pv("1"), unit_price=pv("10.00", currency="INR"),
                     line_total=pv("10.00", currency="USD")),
        ])
        assert format_completeness.check_currency_format(
            ctx(mixed, "CHK-FORMAT-CURRENCY-001")).status == FindingStatus.FAIL

    def test_currency_skips_blank_values(self):
        li = line(1, "1", "10.00", "10.00")
        li.quantity = pv("", raw="")
        d = doc(lines=[li])
        assert format_completeness.check_currency_format(
            ctx(d, "CHK-FORMAT-CURRENCY-001")).status == FindingStatus.PASS

    def test_amount_in_words_is_deferred_not_passed(self):
        r = format_completeness.check_amount_in_words(
            ctx(doc(), "CHK-FORMAT-WORDS-001"))
        assert r.status == FindingStatus.SKIPPED


class TestDuplicate:
    def test_duplicate_skips_rather_than_passing(self):
        """An unimplemented corpus check must never report a document compliant."""
        r = duplicate.check_duplicate_document(ctx(doc(), "CHK-ARITH-LINE-001"))
        assert r.status == FindingStatus.SKIPPED
