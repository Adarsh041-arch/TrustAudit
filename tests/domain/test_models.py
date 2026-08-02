"""Tests for domain models."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from audit_v2.domain.models import (
    Coverage,
    ProvenancedValue,
    ToleranceSpec,
    LineItem,
    CheckResult,
    FindingStatus,
)



class TestProvenancedValue:
    def test_valid_provenanced_value(self):
        pv = ProvenancedValue(value="150.00", raw="$150.00", page=1, confidence=0.97)
        assert pv.decimal_value == Decimal("150.00")

    def test_bbox_must_have_4_elements(self):
        with pytest.raises(ValueError):
            ProvenancedValue(value="10", raw="10", page=1, bbox=[1, 2, 3])

    def test_null_bbox_allowed(self):
        pv = ProvenancedValue(value="10", raw="10", page=1, bbox=None)
        assert pv.bbox is None

    def test_confidence_clamped(self):
        with pytest.raises(ValidationError):
            ProvenancedValue(value="10", raw="10", page=1, confidence=1.5)


class TestCoverage:
    def test_complete_coverage(self):
        c = Coverage(pages_total=5, pages_examined=5, pages_unreadable=[], coverage_complete=True)
        assert c.coverage_complete is True

    def test_incomplete_coverage(self):
        c = Coverage(pages_total=18, pages_examined=10, pages_unreadable=[11], coverage_complete=False)
        assert c.coverage_complete is False

    def test_complete_requires_equal_pages(self):
        with pytest.raises((AssertionError, ValidationError)):
            Coverage(pages_total=5, pages_examined=3, pages_unreadable=[], coverage_complete=True)

    def test_complete_requires_no_unreadable(self):
        with pytest.raises((AssertionError, ValidationError)):
            Coverage(pages_total=5, pages_examined=5, pages_unreadable=[3], coverage_complete=True)


class TestToleranceSpec:
    def test_absolute_tolerance(self):
        t = ToleranceSpec(type="absolute", value="0.01", currency_scaled=True)
        assert t.as_decimal() == Decimal("0.01")

    def test_none_tolerance(self):
        t = ToleranceSpec(type="none", value="0")
        assert t.apply(Decimal("100")) == Decimal("0")

    def test_relative_tolerance(self):
        t = ToleranceSpec(type="relative", value="5", currency_scaled=False)
        assert t.apply(Decimal("100")) == Decimal("5")


class TestLineItem:
    def test_expected_total_correct(self):
        li = LineItem(
            line_number=1,
            description=ProvenancedValue(value="Widget", raw="Widget", page=1),
            quantity=ProvenancedValue(value="5", raw="5", page=1),
            unit_price=ProvenancedValue(value="30.00", raw="$30.00", page=1),
            line_total=ProvenancedValue(value="150.00", raw="$150.00", page=1),
        )
        assert li.expected_total() == Decimal("150.00")

    def test_expected_total_rounding(self):
        li = LineItem(
            line_number=1,
            description=ProvenancedValue(value="Widget", raw="Widget", page=1),
            quantity=ProvenancedValue(value="3", raw="3", page=1),
            unit_price=ProvenancedValue(value="99.99", raw="$99.99", page=1),
            line_total=ProvenancedValue(value="299.97", raw="$299.97", page=1),
        )
        assert li.expected_total() == Decimal("299.97")

    def test_expected_total_zero_decimal_currency(self):
        li = LineItem(
            line_number=1,
            description=ProvenancedValue(value="Widget", raw="Widget", page=1),
            quantity=ProvenancedValue(value="3", raw="3", page=1),
            unit_price=ProvenancedValue(value="1000", raw="JPY 1000", page=1),
            line_total=ProvenancedValue(value="3000", raw="JPY 3000", page=1),
        )
        assert li.expected_total(Decimal("1")) == Decimal("3000")

    def test_hsn_optional(self):
        li = LineItem(
            line_number=1,
            description=ProvenancedValue(value="Service", raw="Service", page=1),
            quantity=ProvenancedValue(value="1", raw="1", page=1),
            unit_price=ProvenancedValue(value="1000.00", raw="$1000.00", page=1),
            line_total=ProvenancedValue(value="1000.00", raw="$1000.00", page=1),
        )
        assert li.hsn_sac is None


class TestCheckResult:
    def test_passed_result(self):
        r = CheckResult.passed("CHK-TEST-001")
        assert r.status == FindingStatus.PASS
        assert r.check_id == "CHK-TEST-001"

    def test_failed_result(self):
        r = CheckResult.failed("CHK-TEST-001", expected="150.00", actual="200.00", delta="50.00")
        assert r.status == FindingStatus.FAIL
        assert r.expected == "150.00"
        assert r.actual == "200.00"

    def test_skipped_result(self):
        r = CheckResult.skipped("CHK-TEST-001", reason="Not applicable")
        assert r.status == FindingStatus.SKIPPED
        assert r.message == "Not applicable"

    def test_failed_with_evidence(self, sample_evidence):
        r = CheckResult.failed(
            "CHK-TEST-001", expected="150.00", actual="200.00", delta="50.00",
            evidence=sample_evidence,
        )
        assert len(r.evidence) == 2
