"""Format/completeness validators — CHK-FORMAT-* checks.

CHK-FORMAT-WORDS-001 is model_assisted and skipped (model call in Phase 8).
"""
import re

from audit_v2.domain.models import (
    CheckContext,
    CheckResult,
    DocumentType,
)

CURRENCY_PATTERN = re.compile(r"^[\u20b9\u0024\u00a3\u20ac]?\s*-?[\d,]+\.?\d*$")

MANDATORY_FIELDS_BY_TYPE = {
    DocumentType.INVOICE: [
        "vendor_name", "vendor_gstin", "invoice_date", "grand_total",
    ],
    DocumentType.PURCHASE_ORDER: [
        "vendor_name", "order_date",
    ],
    DocumentType.DELIVERY_CHALLAN: [
        "vendor_name", "delivery_date",
    ],
    DocumentType.GOODS_RECEIPT_NOTE: [
        "vendor_name", "grn_date",
    ],
}


def check_mandatory_fields(ctx: CheckContext) -> CheckResult:
    """CHK-FORMAT-MANDATORY-001 — all mandatory fields are present."""
    doc = ctx.document
    doc_type = doc.doc_type
    mandatory = MANDATORY_FIELDS_BY_TYPE.get(doc_type, [])
    missing = []
    for field in mandatory:
        val = getattr(doc.header, field, None)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(field)
    if missing:
        return CheckResult.failed(
            "CHK-FORMAT-MANDATORY-001",
            expected="all mandatory fields",
            actual=f"missing: {', '.join(missing)}",
            delta="N/A",
            message=f"Missing mandatory field(s): {', '.join(missing)}",
        )
    return CheckResult.passed("CHK-FORMAT-MANDATORY-001")


def check_line_item_fields(ctx: CheckContext) -> CheckResult:
    """CHK-FORMAT-MANDATORY-002 — line items have required sub-fields."""
    doc = ctx.document
    for line in doc.line_items:
        if line.description is None or not line.description.value.strip():
            return CheckResult.failed(
                "CHK-FORMAT-MANDATORY-002",
                expected="description",
                actual="missing",
                delta="N/A",
                message=f"Line {line.line_number} missing description",
            )
        if line.quantity is None or not line.quantity.value.strip():
            return CheckResult.failed(
                "CHK-FORMAT-MANDATORY-002",
                expected="quantity",
                actual="missing",
                delta="N/A",
                message=f"Line {line.line_number} missing quantity",
            )
        if line.unit_price is None or not line.unit_price.value.strip():
            return CheckResult.failed(
                "CHK-FORMAT-MANDATORY-002",
                expected="unit_price",
                actual="missing",
                delta="N/A",
                message=f"Line {line.line_number} missing unit_price",
            )
        if line.line_total is None or not line.line_total.value.strip():
            return CheckResult.failed(
                "CHK-FORMAT-MANDATORY-002",
                expected="line_total",
                actual="missing",
                delta="N/A",
                message=f"Line {line.line_number} missing line_total",
            )
    return CheckResult.passed("CHK-FORMAT-MANDATORY-002")


def check_tax_breakdown(ctx: CheckContext) -> CheckResult:
    """CHK-FORMAT-TAXBREAKDOWN-001 — tax lines have all required breakdown fields."""
    doc = ctx.document
    for tax_line in doc.tax_lines:
        for field in ("taxable_value", "rate", "cgst", "sgst", "total_tax"):
            val = getattr(tax_line, field, None)
            if val is None or not val.value.strip():
                return CheckResult.failed(
                    "CHK-FORMAT-TAXBREAKDOWN-001",
                    expected=field,
                    actual="missing",
                    delta="N/A",
                    message=f"Tax line {tax_line.line_number} missing required field: {field}",
                )
    return CheckResult.passed("CHK-FORMAT-TAXBREAKDOWN-001")


def check_currency_format(ctx: CheckContext) -> CheckResult:
    """CHK-FORMAT-CURRENCY-001 — all monetary values use consistent currency format."""
    doc = ctx.document
    seen_currency = None
    for line in doc.line_items:
        for field_name, pv in [
            ("quantity", line.quantity),
            ("unit_price", line.unit_price),
            ("line_total", line.line_total),
        ]:
            if pv is None or not pv.value.strip():
                continue
            if pv.currency is not None:
                if seen_currency is None:
                    seen_currency = pv.currency
                elif pv.currency != seen_currency:
                    return CheckResult.failed(
                        "CHK-FORMAT-CURRENCY-001",
                        expected=f"currency={seen_currency}",
                        actual=f"currency={pv.currency} at {field_name}",
                        delta="N/A",
                        message=f"Inconsistent currency format at {field_name}: {pv.raw}",
                    )
    return CheckResult.passed("CHK-FORMAT-CURRENCY-001")


def check_amount_in_words(ctx: CheckContext) -> CheckResult:
    """CHK-FORMAT-WORDS-001 — amount in words matches total (model_assisted, skipped here)."""
    return CheckResult.skipped(
        "CHK-FORMAT-WORDS-001",
        "Model-assisted check: deferred to Phase 8 (adjudicator)",
    )
