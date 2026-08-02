"""Threshold validators — CHK-THRESHOLD-* checks."""
from decimal import Decimal

from audit_v2.domain.models import CheckContext, CheckResult
from audit_v2.domain.validators.arithmetic import GST_SLAB_RATES


def check_line_threshold(ctx: CheckContext) -> CheckResult:
    """CHK-THRESHOLD-LINE-001 — no line item exceeds document total."""
    doc = ctx.document
    if not doc.line_items:
        return CheckResult.passed("CHK-THRESHOLD-LINE-001")
    if doc.header.grand_total is None:
        return CheckResult.skipped("CHK-THRESHOLD-LINE-001", "No grand total")

    doc_total = doc.header.grand_total.decimal_value
    for line in doc.line_items:
        line_val = line.line_total.decimal_value
        if line_val > doc_total:
            return CheckResult.failed(
                "CHK-THRESHOLD-LINE-001",
                expected=f"≤ {doc_total}",
                actual=str(line_val),
                delta=str(line_val - doc_total),
                message=f"Line {line.line_number} value {line_val} exceeds total {doc_total}",
            )
    return CheckResult.passed("CHK-THRESHOLD-LINE-001")


def check_discount_threshold(ctx: CheckContext) -> CheckResult:
    """CHK-THRESHOLD-DISC-001 — discount percentage is within allowed range."""
    doc = ctx.document
    if doc.header.discount_percentage is None:
        return CheckResult.skipped("CHK-THRESHOLD-DISC-001", "No discount percentage")

    disc_pct = doc.header.discount_percentage.decimal_value
    if disc_pct < Decimal("0"):
        return CheckResult.failed(
            "CHK-THRESHOLD-DISC-001",
            expected="≥ 0",
            actual=str(disc_pct),
            delta=str(abs(disc_pct)),
            message=f"Discount {disc_pct}% is outside allowed range [0, 100]",
        )
    if disc_pct > Decimal("100"):
        return CheckResult.failed(
            "CHK-THRESHOLD-DISC-001",
            expected="≤ 100%",
            actual=str(disc_pct),
            delta=str(disc_pct - Decimal("100")),
            message=f"Discount {disc_pct}% is outside allowed range [0, 100]",
        )
    return CheckResult.passed("CHK-THRESHOLD-DISC-001")


def check_tax_rate_threshold(ctx: CheckContext) -> CheckResult:
    """CHK-THRESHOLD-TAXRATE-001 — tax rate is within valid GST slab."""
    doc = ctx.document
    for tax_line in doc.tax_lines:
        rate = tax_line.rate.decimal_value
        if rate not in GST_SLAB_RATES:
            return CheckResult.failed(
                "CHK-THRESHOLD-TAXRATE-001",
                expected="valid GST slab",
                actual=str(rate),
                delta="N/A",
                message=f"Tax rate {rate}% is not a valid GST slab rate",
            )
    return CheckResult.passed("CHK-THRESHOLD-TAXRATE-001")
