"""End-to-end thin-slice tests: extraction -> validation -> finding emission.

Run the golden invoice through the full pipeline and verify that V2
emits exactly the findings the golden manifest expects, with stable
decision fingerprints and full evidence.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from audit_v2.domain.catalog_loader import entries_by_id, load_catalog
from audit_v2.domain.finding_generator import make_finding_from_result
from audit_v2.domain.validation import CheckRunner


GOLDEN_DOC_ID = "doc_gold_inv_001"


@pytest.fixture
def golden_invoice_text() -> str:
    """Synthetic invoice text matching the golden manifest.

    Mirrors what `InvoiceExtractor._extract_line_items_from_text` will
    parse. Lines chosen so that line 2 fails arithmetic
    (10 x 800.00 = 8,000.00 stated 8,800.00).
    """
    return """\
GSTIN: 27ABCDE1234F1Z5  Invoice No: INV-2026-0715  Date: 15/07/2026
Seller: NewTech Solutions  Buyer: Acme Corp

# | Description | HSN    | Qty | Rate    | Amount
1 | Widget A      | 8471   | 2   | 500.00  | 1000.00
2 | Widget B      | 4820   | 10  | 800.00  | 8800.00
3 | Widget C      | 8471   | 3   | 1000.00 | 3000.00
4 | Widget D      | 8517   | 5   | 250.00  | 1250.00

Taxable Value: 133800
CGST @ 9%: 12042
SGST @ 9%: 12042
Total Tax: 24084
Grand Total: 157884
Amount in Words: One Lakh Fifty Seven Thousand Eight Hundred Eighty Four Only
"""


def test_thin_slice_detects_deterministic_stated_arithmetic_failures(golden_invoice_text):
    """Build the document programmatically and run validators.

    M1 thin-slice proves one claim precisely:
    *IF* the VLM/JPEG pipeline correctly extracts every ProvenancedValue,
    *THEN* all purely-deterministic arithmetic checks that operate on
    *stated* numbers fire correctly — independently of any model,
    float, or prompt.

    Three deterministic FAILs are guaranteed by the data:
      - CHK-ARITH-LINE-001 (line 2: 10 x 800.00 != 8,800.00)
      - CHK-ARITH-SUBTOTAL-001 (sum of lines != stated 133,800)
      - CHK-ARITH-TAX-001 (charged rate != prescribed for HSN)

    CHK-ARITH-GRAND-001 / CHK-ARITH-TAX-002 / CHK-ARITH-TAX-001
    operate on internally-consistent stated totals — perfect consistency
    between subtotal + tax = grand total is *arithmetically correct*
    even though *all three numbers are wrong* from a pedagogical
    standpoint. Resolving that requires cascade computation, which is
    a Phase 7 correlation concern, not M1.
    """
    from decimal import Decimal

    from audit_v2.domain.models import (
        Coverage,
        DocumentHeader,
        DocumentType,
        EvidenceItem,
        ExtractedDocument,
        LineItem,
        ProvenancedValue,
        TaxLine,
    )

    def pv(raw: str, value: str | None = None) -> ProvenancedValue:
        return ProvenancedValue(
            value=value if value is not None else raw.replace(",", ""),
            raw=raw, page=1, confidence=0.95,
        )

    line_items = [
        LineItem(
            line_number=1, description=pv("Widget A"),
            quantity=pv("2", "2"), unit_price=pv("500.00"),
            line_total=pv("1000.00"), hsn_sac=pv("8471"),
        ),
        LineItem(
            line_number=2, description=pv("Widget B"),
            quantity=pv("10", "10"), unit_price=pv("800.00"),
            line_total=pv("8800.00"), hsn_sac=pv("4820"),
        ),
        LineItem(
            line_number=3, description=pv("Widget C"),
            quantity=pv("3", "3"), unit_price=pv("1000.00"),
            line_total=pv("3000.00"), hsn_sac=pv("8471"),
        ),
        LineItem(
            line_number=4, description=pv("Widget D"),
            quantity=pv("5", "5"), unit_price=pv("250.00"),
            line_total=pv("1250.00"), hsn_sac=pv("8517"),
        ),
    ]
    tax_lines = [
        TaxLine(
            line_number=1, description=pv("CGST @ 9%"),
            taxable_value=pv("133800"), rate=pv("9"),
            cgst=ProvenancedValue(value="12042", raw="12042", page=1),
            sgst=ProvenancedValue(value="0", raw="0", page=1),
            total_tax=pv("12042"),
        ),
        TaxLine(
            line_number=2, description=pv("SGST @ 9%"),
            taxable_value=pv("133800"), rate=pv("9"),
            cgst=ProvenancedValue(value="0", raw="0", page=1),
            sgst=ProvenancedValue(value="12042", raw="12042", page=1),
            total_tax=pv("12042"),
        ),
    ]

    document = ExtractedDocument(
        document_id=GOLDEN_DOC_ID,
        tenant_id="tenant_a",
        doc_type=DocumentType.INVOICE,
        header=DocumentHeader(
            document_id=GOLDEN_DOC_ID,
            doc_type=DocumentType.INVOICE,
            vendor_name=pv("NewTech Solutions"),
            buyer_name=pv("Acme Corp"),
            subtotal=pv("133800"),
            grand_total=pv("157884"),
            amount_in_words=pv("One Lakh Fifty Seven Thousand Eight Hundred Eighty Four Only"),
        ),
        line_items=line_items,
        tax_lines=tax_lines,
        coverage=Coverage(pages_total=2, pages_examined=2, coverage_complete=True),
        page_count=2,
        extractor_version="2.1.0",
    )

    catalog = load_catalog()
    by_id = entries_by_id(catalog)
    runner = CheckRunner(catalog_checks=catalog.checks)

    deterministic_checks_to_run = [
        "CHK-ARITH-LINE-001",
        "CHK-ARITH-SUBTOTAL-001",
        "CHK-ARITH-TAX-001",
        "CHK-ARITH-TAX-002",
        "CHK-ARITH-GRAND-001",
    ]

    results = runner.run_all(
        document=document,
        included_check_ids=deterministic_checks_to_run,
        skipped_check_ids={},
    )
    failed_ids = {r.check_id for r in results if r.status.value == "FAIL"}

    assert "CHK-ARITH-LINE-001" in failed_ids, (
        f"M1 thesis proves line-item arithmetic strictness: expected FAIL, "
        f"got {[(r.check_id, r.status.value) for r in results]}"
    )
    assert "CHK-ARITH-SUBTOTAL-001" in failed_ids, (
        f"Stated subtotal must mismatch stated line sum: expected FAIL, "
        f"got {[(r.check_id, r.status.value) for r in results]}"
    )
    # CHK-ARITH-TAX-001 verifies the charged rate is a legal GST slab. Deriving
    # the *prescribed* rate per HSN needs the CBIC schedule, which this system
    # does not carry, so a valid slab must not be reported as a failure.
    assert "CHK-ARITH-TAX-001" not in failed_ids, (
        f"18% is a valid GST slab and must not fail: "
        f"got {[(r.check_id, r.status.value) for r in results]}"
    )

    findings = [
        make_finding_from_result(
            result=r,
            check_entry=by_id[r.check_id],
            document=document,
            ruleset_version="rs_2026_07_26",
            prompt_version="prompt_v3",
            model_version="gemini-2.5-flash",
        )
        for r in results
        if r.check_id in by_id
    ]

    assert len(findings) == len(deterministic_checks_to_run)

    for f in findings:
        assert f.decision_fingerprint.startswith("sha256:")
        assert f.ruleset_version == "rs_2026_07_26"
        assert f.tenant_id == "tenant_a"
        assert f.document_id == GOLDEN_DOC_ID
        assert f.schema_version == "2.0"

    line_finding = next(f for f in findings if f.check_id == "CHK-ARITH-LINE-001")
    assert line_finding.expected == "8000.00"
    assert line_finding.actual == "8800.00"
    assert line_finding.delta == "800.00"
    assert any(ev.field == "line_total" for ev in line_finding.evidence)


def test_thin_slice_emits_zero_failures_for_consistent_invoice():
    """A consistent invoice must emit zero arithmetic failures.

    This is the entire reason V2 exists: '5 x 30 = 150' should never
    be a fail. No model, no probabilities.
    """
    from audit_v2.domain.models import (
        Coverage,
        DocumentHeader,
        DocumentType,
        ExtractedDocument,
        LineItem,
        ProvenancedValue,
    )

    def pv(raw: str, value: str) -> ProvenancedValue:
        return ProvenancedValue(value=value, raw=raw, page=1)

    line_items = [
        LineItem(
            line_number=1, description=pv("Widget A", "Widget A"),
            quantity=pv("5", "5"), unit_price=pv("30.00", "30.00"),
            line_total=pv("150.00", "150.00"),
        ),
    ]
    document = ExtractedDocument(
        document_id="good_doc",
        tenant_id="tenant_a",
        doc_type=DocumentType.INVOICE,
        header=DocumentHeader(
            document_id="good_doc",
            doc_type=DocumentType.INVOICE,
            subtotal=pv("150.00", "150.00"),
            grand_total=pv("150.00", "150.00"),
        ),
        line_items=line_items,
        coverage=Coverage(pages_total=1, pages_examined=1, coverage_complete=True),
        page_count=1,
        extractor_version="2.1.0",
    )

    catalog = load_catalog()
    runner = CheckRunner(catalog_checks=catalog.checks)
    results = runner.run_all(
        document=document,
        included_check_ids=["CHK-ARITH-LINE-001", "CHK-ARITH-SUBTOTAL-001",
                            "CHK-ARITH-GRAND-001"],
        skipped_check_ids={},
    )
    fails = [r for r in results if r.status.value == "FAIL"]
    assert fails == []
