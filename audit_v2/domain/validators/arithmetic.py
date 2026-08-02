"""Arithmetic validators — CHK-ARITH-* checks.

All validators are pure Python functions using Decimal arithmetic.
They make no network or model calls.
"""
from decimal import ROUND_HALF_UP, Decimal

from audit_v2.domain.models import (
    CheckContext,
    CheckResult,
    EvidenceItem,
    ProvenancedValue,
)

# Full GST slabs, plus the CGST/SGST component halves. An 18% slab is levied as

# CGST 9% + SGST 9%, so each component line legitimately carries half the slab.
GST_SLAB_RATES = {
    Decimal("0"), Decimal("0.125"), Decimal("0.25"), Decimal("0.5"),
    Decimal("1"), Decimal("1.5"), Decimal("2.5"), Decimal("3"),
    Decimal("5"), Decimal("6"), Decimal("9"), Decimal("12"),
    Decimal("14"), Decimal("18"), Decimal("28"),
}

DEFAULT_MAX_DISCOUNT_PCT = "20"


def check_line_total(ctx: CheckContext) -> CheckResult:
    """CHK-ARITH-LINE-001 — each line_total must equal quantity * unit_price."""
    doc = ctx.document
    for line in doc.line_items:
        expected = line.expected_total(ctx.currency_exponent)
        actual = line.line_total.decimal_value
        delta = abs(actual - expected)
        if delta > ctx.tolerance_for("CHK-ARITH-LINE-001"):
            return CheckResult.failed(
                "CHK-ARITH-LINE-001",
                expected=str(expected),
                actual=str(actual),
                delta=str(delta),
                message=f"Line {line.line_number}: {line.quantity.raw} x {line.unit_price.raw} "
                        f"= {expected}, stated {actual}",
                evidence=[_evidence(ctx, line.line_total, "line_total")],
            )
    return CheckResult.passed("CHK-ARITH-LINE-001")


def check_subtotal_tieout(ctx: CheckContext) -> CheckResult:
    """CHK-ARITH-SUBTOTAL-001 — sum of line totals equals stated subtotal."""
    doc = ctx.document
    if not doc.line_items:
        return CheckResult.skipped("CHK-ARITH-SUBTOTAL-001", "No line items")
    if doc.header.subtotal is None:
        return CheckResult.skipped("CHK-ARITH-SUBTOTAL-001", "No subtotal field")

    line_sum = sum(Decimal(li.line_total.value) for li in doc.line_items)
    stated = doc.header.subtotal.decimal_value
    delta = abs(line_sum - stated)
    if delta > ctx.tolerance_for("CHK-ARITH-SUBTOTAL-001"):
        return CheckResult.failed(
            "CHK-ARITH-SUBTOTAL-001",
            expected=str(line_sum),
            actual=str(stated),
            delta=str(delta),
            message=f"Line total sum {line_sum} != stated subtotal {stated}",
            evidence=[_evidence(ctx, doc.header.subtotal, "subtotal")],
        )
    return CheckResult.passed("CHK-ARITH-SUBTOTAL-001")


def check_tax_rate(ctx: CheckContext) -> CheckResult:
    """CHK-ARITH-TAX-001 — charged tax rate is a valid GST slab.

    Verifying the *prescribed* rate for a given HSN requires the CBIC rate
    schedule, which this system does not carry. Guessing it from the HSN prefix
    produces confidently wrong findings, so we verify only what is checkable
    deterministically: that the charged rate is a legal slab. Per-HSN rate
    correctness needs the rate table and is escalated, not fabricated.
    """
    doc = ctx.document
    if not doc.tax_lines:
        return CheckResult.skipped("CHK-ARITH-TAX-001", "No tax lines")

    for tax_line in doc.tax_lines:
        charged_rate = tax_line.rate.decimal_value
        if charged_rate not in GST_SLAB_RATES:
            return CheckResult.failed(
                "CHK-ARITH-TAX-001",
                expected="one of " + ", ".join(str(r) for r in sorted(GST_SLAB_RATES)),
                actual=str(charged_rate),
                delta="N/A",
                message=f"Tax rate {charged_rate}% is not a valid GST slab rate",
                evidence=[_evidence(ctx, tax_line.rate, "rate")],
            )
    return CheckResult.passed("CHK-ARITH-TAX-001")


def check_tax_calculation(ctx: CheckContext) -> CheckResult:
    """CHK-ARITH-TAX-002 — CGST + SGST equals total tax, both calculated correctly."""
    doc = ctx.document
    for tax_line in doc.tax_lines:
        cgst = tax_line.cgst.decimal_value
        sgst = tax_line.sgst.decimal_value
        total_tax = tax_line.total_tax.decimal_value
        calculated = cgst + sgst
        delta = abs(calculated - total_tax)
        if delta > ctx.tolerance_for("CHK-ARITH-TAX-002"):
            return CheckResult.failed(
                "CHK-ARITH-TAX-002",
                expected=str(calculated),
                actual=str(total_tax),
                delta=str(delta),
                message=f"CGST {cgst} + SGST {sgst} = {calculated}, stated {total_tax}",
                evidence=[
                    _evidence(ctx, tax_line.cgst, "cgst"),
                    _evidence(ctx, tax_line.sgst, "sgst"),
                ],
            )
        taxable = tax_line.taxable_value.decimal_value
        rate = tax_line.rate.decimal_value
        if taxable == 0 or rate == 0:
            # Taxable base was not extracted; recomputing against zero would
            # manufacture a failure for every tax line.
            continue
        expected_tax = (taxable * rate / Decimal("100")).quantize(
            ctx.currency_exponent, rounding=ROUND_HALF_UP,
        )
        if abs(expected_tax - total_tax) > ctx.tolerance_for("CHK-ARITH-TAX-002"):
            return CheckResult.failed(
                "CHK-ARITH-TAX-002",
                expected=str(expected_tax),
                actual=str(total_tax),
                delta=str(abs(expected_tax - total_tax)),
                message=f"Taxable {taxable} x rate {rate}% = {expected_tax}, stated {total_tax}",
            )
    return CheckResult.passed("CHK-ARITH-TAX-002")


def check_discount_cap(ctx: CheckContext) -> CheckResult:
    """CHK-ARITH-DISCOUNT-001 — discount percentage does not exceed tenant maximum."""
    doc = ctx.document
    if doc.header.discount_percentage is None:
        return CheckResult.skipped("CHK-ARITH-DISCOUNT-001", "No discount_percentage")

    disc_pct = doc.header.discount_percentage.decimal_value
    max_pct = Decimal(
        ctx.tenant_tolerances.get("MAX_DISCOUNT_PCT", DEFAULT_MAX_DISCOUNT_PCT)
    )
    # Both sides are percentages; the catalog tolerance is a percentage-point
    # allowance, not a fraction of the subtotal.
    delta = disc_pct - max_pct
    if delta > ctx.check_entry.tolerance.as_decimal():
        return CheckResult.failed(
            "CHK-ARITH-DISCOUNT-001",
            expected=f"max {max_pct}%",
            actual=f"{disc_pct}%",
            delta=str(delta),
            message=f"Discount {disc_pct}% exceeds maximum permitted {max_pct}%",
            evidence=[_evidence(ctx, doc.header.discount_percentage, "discount_percentage")],
        )
    return CheckResult.passed("CHK-ARITH-DISCOUNT-001")


def check_grand_total(ctx: CheckContext) -> CheckResult:
    """CHK-ARITH-GRAND-001 — grand_total equals subtotal + tax - discount."""
    doc = ctx.document
    if doc.header.grand_total is None:
        return CheckResult.skipped("CHK-ARITH-GRAND-001", "No grand_total")
    if doc.header.subtotal is None:
        return CheckResult.skipped("CHK-ARITH-GRAND-001", "No subtotal")

    subtotal = doc.header.subtotal.decimal_value
    tax_total = sum(tl.total_tax.decimal_value for tl in doc.tax_lines)
    discount = Decimal("0")
    if doc.header.discount_amount is not None:
        discount = doc.header.discount_amount.decimal_value
    expected = subtotal + tax_total - discount
    actual = doc.header.grand_total.decimal_value
    delta = abs(expected - actual)
    if delta > ctx.tolerance_for("CHK-ARITH-GRAND-001"):
        return CheckResult.failed(
            "CHK-ARITH-GRAND-001",
            expected=str(expected),
            actual=str(actual),
            delta=str(delta),
            message=f"Subtotal {subtotal} + tax {tax_total} - discount {discount} "
                    f"= {expected}, stated {actual}",
            evidence=[_evidence(ctx, doc.header.grand_total, "grand_total")],
        )
    return CheckResult.passed("CHK-ARITH-GRAND-001")


def check_rounding_accumulation(ctx: CheckContext) -> CheckResult:
    """CHK-ARITH-ROUNDING-001 — per-line rounding accumulates within tolerance."""
    doc = ctx.document
    if not doc.line_items:
        return CheckResult.passed("CHK-ARITH-ROUNDING-001")

    grand = Decimal("0")
    for line in doc.line_items:
        expected = line.expected_total(ctx.currency_exponent)
        stated = line.line_total.decimal_value
        grand += expected - stated

    delta = abs(grand)
    tolerance = ctx.tolerance_for("CHK-ARITH-ROUNDING-001")
    if delta > tolerance:
        return CheckResult.failed(
            "CHK-ARITH-ROUNDING-001",
            expected="0",
            actual=str(grand),
            delta=str(delta),
            message=f"Rounding discrepancy {grand} exceeds tolerance "
                        f"for {len(doc.line_items)} lines",
        )
    return CheckResult.passed("CHK-ARITH-ROUNDING-001")


def _evidence(ctx: CheckContext, pv: ProvenancedValue, field: str) -> EvidenceItem:

    return EvidenceItem(
        document_id=ctx.document.document_id,
        page=pv.page,
        bbox=pv.bbox or [],
        field=field,
        raw=pv.raw,
    )
