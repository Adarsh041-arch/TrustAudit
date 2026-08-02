"""Tests for arithmetic validators."""


from audit_v2.domain.models import (
    CheckCatalogEntry,
    CheckContext,
    CheckDeterminism,
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
    FindingStatus,
    LineItem,
    ProvenancedValue,
    Severity,
    ToleranceSpec,
)
from audit_v2.domain.validators.arithmetic import check_line_total


def make_context(
    line_items: list[LineItem] | None = None,
    tolerance_value: str = "0.00",
) -> CheckContext:
    entry = CheckCatalogEntry(
        check_id="CHK-ARITH-LINE-001",
        title="Line-item total equals quantity times unit price",
        category="arithmetic",
        applies_to=[DocumentType.INVOICE, DocumentType.PURCHASE_ORDER],
        severity=Severity.CRITICAL,
        determinism=CheckDeterminism.DETERMINISTIC,
        inputs=["line_items"],
        tolerance=ToleranceSpec(type="absolute", value=tolerance_value, currency_scaled=True),
        failure_message="Line {n}: {qty} x {unit_price} = {expected}, stated {actual}",
    )
    doc = ExtractedDocument(
        document_id="doc_test",
        tenant_id="tenant-a",
        doc_type=DocumentType.INVOICE,
        header=DocumentHeader(document_id="doc_test", doc_type=DocumentType.INVOICE),
        line_items=line_items or [],
        coverage=Coverage(pages_total=1, pages_examined=1, pages_unreadable=[], coverage_complete=True),
        page_count=1,
        extractor_version="1.0.0",
    )
    return CheckContext(document=doc, check_entry=entry)


class TestCheckLineTotal:
    def test_passes_when_correct(self):
        line = LineItem(
            line_number=1,
            description=ProvenancedValue(value="Widget", raw="Widget", page=1),
            quantity=ProvenancedValue(value="5", raw="5", page=1),
            unit_price=ProvenancedValue(value="30.00", raw="$30.00", page=1),
            line_total=ProvenancedValue(value="150.00", raw="$150.00", page=1),
        )
        ctx = make_context(line_items=[line])
        result = check_line_total(ctx)
        assert result.status == FindingStatus.PASS

    def test_fails_when_incorrect(self):
        line = LineItem(
            line_number=2,
            description=ProvenancedValue(value="Widget B", raw="Widget B", page=1),
            quantity=ProvenancedValue(value="10", raw="10", page=1),
            unit_price=ProvenancedValue(value="800.00", raw="$800.00", page=1),
            line_total=ProvenancedValue(value="8800.00", raw="$8800.00", page=1),
        )
        ctx = make_context(line_items=[line])
        result = check_line_total(ctx)
        assert result.status == FindingStatus.FAIL
        assert result.expected == "8000.00"
        assert result.actual == "8800.00"

    def test_passes_within_tolerance(self):
        line = LineItem(
            line_number=1,
            description=ProvenancedValue(value="Widget", raw="Widget", page=1),
            quantity=ProvenancedValue(value="3", raw="3", page=1),
            unit_price=ProvenancedValue(value="10.00", raw="$10.00", page=1),
            line_total=ProvenancedValue(value="30.01", raw="$30.01", page=1),
        )
        ctx = make_context(line_items=[line], tolerance_value="0.02")
        result = check_line_total(ctx)
        assert result.status == FindingStatus.PASS

    def test_fails_outside_tolerance(self):
        line = LineItem(
            line_number=1,
            description=ProvenancedValue(value="Widget", raw="Widget", page=1),
            quantity=ProvenancedValue(value="3", raw="3", page=1),
            unit_price=ProvenancedValue(value="10.00", raw="$10.00", page=1),
            line_total=ProvenancedValue(value="30.10", raw="$30.10", page=1),
        )
        ctx = make_context(line_items=[line], tolerance_value="0.05")
        result = check_line_total(ctx)
        assert result.status == FindingStatus.FAIL

    def test_large_numbers(self):
        line = LineItem(
            line_number=1,
            description=ProvenancedValue(value="Server Rack", raw="Server Rack", page=1),
            quantity=ProvenancedValue(value="100", raw="100", page=1),
            unit_price=ProvenancedValue(value="125000.00", raw="125000.00", page=1),
            line_total=ProvenancedValue(value="12500000.00", raw="12500000.00", page=1),
        )
        ctx = make_context(line_items=[line])
        result = check_line_total(ctx)
        assert result.status == FindingStatus.PASS

    def test_zero_quantity(self):
        line = LineItem(
            line_number=1,
            description=ProvenancedValue(value="Free Item", raw="Free Item", page=1),
            quantity=ProvenancedValue(value="0", raw="0", page=1),
            unit_price=ProvenancedValue(value="100.00", raw="$100.00", page=1),
            line_total=ProvenancedValue(value="0.00", raw="$0.00", page=1),
        )
        ctx = make_context(line_items=[line])
        result = check_line_total(ctx)
        assert result.status == FindingStatus.PASS