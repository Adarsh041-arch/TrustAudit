"""M1 thin slice tests — Emission layer: CheckResult -> Finding with fingerprint."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from audit_v2.domain.finding_generator import make_finding_from_result
from audit_v2.domain.models import (
    CheckCatalogEntry,
    CheckResult,
    Coverage,
    DocumentHeader,
    EvidenceItem,
    ExtractedDocument,
    FindingStatus,
    ProvenancedValue,
    Severity,
    ToleranceSpec,
)


@pytest.fixture
def catalog_entry() -> CheckCatalogEntry:
    return CheckCatalogEntry(
        check_id="CHK-ARITH-LINE-001",
        title="Line-item total equals quantity times unit price",
        category="arithmetic",
        applies_to=["invoice"],
        severity="critical",
        determinism="deterministic",
        inputs=["line_items"],
        tolerance=ToleranceSpec(type="absolute", value="0.00", currency_scaled=True),
        failure_message="Line {n}: {qty} x {unit_price} = {expected}, stated {actual}",
        ruleset_version="rs_2026_07_26",
    )


@pytest.fixture
def sample_document() -> ExtractedDocument:
    return ExtractedDocument(
        document_id="doc_test_001",
        tenant_id="tenant_a",
        doc_type="invoice",
        header=DocumentHeader(
            document_id="doc_test_001",
            doc_type="invoice",
            vendor_name=ProvenancedValue(value="Acme", raw="Acme", page=1),
            buyer_name=ProvenancedValue(value="Globex", raw="Globex", page=1),
        ),
        line_items=[],
        coverage=Coverage(pages_total=2, pages_examined=2, coverage_complete=True),
        page_count=2,
        extractor_version="2.1.0",
    )


def test_make_finding_from_pass_result_emits_pass_finding(
    catalog_entry, sample_document
):
    result = CheckResult.passed("CHK-ARITH-LINE-001")
    finding = make_finding_from_result(
        result=result,
        check_entry=catalog_entry,
        document=sample_document,
        ruleset_version="rs_2026_07_26",
        prompt_version="prompt_v3",
        model_version="gemini-2.5-flash",
    )
    assert finding.check_id == "CHK-ARITH-LINE-001"
    assert finding.status == FindingStatus.PASS
    assert finding.tenant_id == "tenant_a"
    assert finding.document_id == "doc_test_001"
    assert finding.ruleset_version == "rs_2026_07_26"
    assert finding.decision_fingerprint.startswith("sha256:")
    assert finding.schema_version == "2.0"


def test_make_finding_from_fail_result_includes_evidence_and_delta(
    catalog_entry, sample_document
):
    evidence = [
        EvidenceItem(
            document_id="doc_test_001",
            page=1,
            bbox=[100, 200, 150, 220],
            field="line_total",
            raw="200.00",
        )
    ]
    result = CheckResult.failed(
        "CHK-ARITH-LINE-001",
        expected="150.00",
        actual="200.00",
        delta="50.00",
        evidence=evidence,
        message="Line 1: 5 x 30.00 = 150.00, stated 200.00",
    )

    finding = make_finding_from_result(
        result=result,
        check_entry=catalog_entry,
        document=sample_document,
        ruleset_version="rs_2026_07_26",
        prompt_version="prompt_v3",
        model_version="gemini-2.5-flash",
    )

    assert finding.status == FindingStatus.FAIL
    assert finding.expected == "150.00"
    assert finding.actual == "200.00"
    assert finding.delta == "50.00"
    assert finding.severity == Severity.CRITICAL
    assert finding.evidence == evidence


def test_decision_fingerprint_is_stable_same_inputs_produce_same_finding(
    catalog_entry, sample_document
):
    result = CheckResult.passed("CHK-ARITH-LINE-001")
    kwargs = dict(
        result=result,
        check_entry=catalog_entry,
        document=sample_document,
        ruleset_version="rs_2026_07_26",
        prompt_version="prompt_v3",
        model_version="gemini-2.5-flash",
    )
    f1 = make_finding_from_result(**kwargs)
    f2 = make_finding_from_result(**kwargs)
    assert f1.decision_fingerprint == f2.decision_fingerprint


def test_decision_fingerprint_changes_when_ruleset_changes(
    catalog_entry, sample_document
):
    result = CheckResult.passed("CHK-ARITH-LINE-001")
    f1 = make_finding_from_result(
        result=result,
        check_entry=catalog_entry,
        document=sample_document,
        ruleset_version="rs_2026_07_26",
        prompt_version="prompt_v3",
        model_version="gemini-2.5-flash",
    )
    f2 = make_finding_from_result(
        result=result,
        check_entry=catalog_entry,
        document=sample_document,
        ruleset_version="rs_2026_08_01",
        prompt_version="prompt_v3",
        model_version="gemini-2.5-flash",
    )
    assert f1.decision_fingerprint != f2.decision_fingerprint
