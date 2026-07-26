"""Reference integrity validators — CHK-REF-* checks.

These are deterministic single-document checks. Cross-document checks (CHK-REF-QTY-001/002)
require corpus context and are deferred to Phase 7.
"""
import re

from audit_v2.domain.models import CheckContext, CheckResult

GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9][Z][0-9A-Z]$")
IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def check_po_reference(ctx: CheckContext) -> CheckResult:
    """CHK-REF-PO-001 — invoice references a valid PO number."""
    doc = ctx.document
    po_ref = doc.header.po_reference
    if po_ref is None or not po_ref.value.strip():
        return CheckResult.failed(
            "CHK-REF-PO-001",
            expected="PO reference",
            actual="missing",
            delta="N/A",
            message="Invoice has no PO reference",
        )
    return CheckResult.passed("CHK-REF-PO-001")


def check_gstin_format(ctx: CheckContext) -> CheckResult:
    """CHK-REF-GST-001 — GSTIN format is valid (15 chars, alphanumeric)."""
    doc = ctx.document
    gstin = doc.header.vendor_gstin
    if gstin is None or not gstin.value.strip():
        return CheckResult.failed(
            "CHK-REF-GST-001",
            expected="valid GSTIN",
            actual="missing",
            delta="N/A",
            message="GSTIN is missing",
        )
    if not GSTIN_PATTERN.match(gstin.value.strip().upper()):
        return CheckResult.failed(
            "CHK-REF-GST-001",
            expected="valid GSTIN (15 chars: 2 alphanumeric + 5 alpha + 4 numeric + 1 alpha + 1 alphanumeric + Z + 1 alphanumeric)",  # noqa: E501
            actual=gstin.value,
            delta="N/A",
            message=f"GSTIN '{gstin.value}' does not match valid format",
        )
    return CheckResult.passed("CHK-REF-GST-001")


def check_hsn_code(ctx: CheckContext) -> CheckResult:
    """CHK-REF-HSN-001 — HSN/SAC code is present and valid.

    Indian HSN is reported at 4, 6 or 8 digits depending on the filer's
    turnover slab; SAC is 6. Requiring 6/8 rejects legitimate 4-digit headings.
    """
    doc = ctx.document
    for line in doc.line_items:
        if line.hsn_sac is None or not line.hsn_sac.value.strip():
            return CheckResult.failed(
                "CHK-REF-HSN-001",
                expected="4, 6 or 8 digit HSN/SAC",
                actual="missing",
                delta="N/A",
                message=f"Line {line.line_number} missing HSN/SAC code",
            )
        hsn = line.hsn_sac.value.strip()
        if not hsn.isdigit() or len(hsn) not in (4, 6, 8):
            return CheckResult.failed(
                "CHK-REF-HSN-001",
                expected="4, 6 or 8 digit HSN/SAC",
                actual=hsn,
                delta="N/A",
                message=f"HSN/SAC '{hsn}' invalid for line {line.line_number}",
            )
    return CheckResult.passed("CHK-REF-HSN-001")


def check_bank_details(ctx: CheckContext) -> CheckResult:
    """CHK-REF-BANK-001 — bank details (account number, IFSC) are present."""
    doc = ctx.document
    bank = doc.header.bank_details
    if bank is None:
        return CheckResult.failed(
            "CHK-REF-BANK-001",
            expected="bank details",
            actual="missing",
            delta="N/A",
            message="Bank details are missing",
        )
    missing = []
    if not bank.get("account_number"):
        missing.append("account_number")
    if not bank.get("ifsc"):
        missing.append("ifsc")
    if missing:
        return CheckResult.failed(
            "CHK-REF-BANK-001",
            expected="account_number and ifsc",
            actual=f"missing: {', '.join(missing)}",
            delta="N/A",
            message=f"Bank details are incomplete: missing {', '.join(missing)}",
        )
    return CheckResult.passed("CHK-REF-BANK-001")


def check_quantity_po(ctx: CheckContext) -> CheckResult:
    """CHK-REF-QTY-001 — invoiced qty <= PO qty (requires corpus context, deferred to Phase 7)."""
    return CheckResult.skipped(
        "CHK-REF-QTY-001",
        "Cross-document check: requires corpus context (Phase 7)",
    )


def check_quantity_dc(ctx: CheckContext) -> CheckResult:
    """CHK-REF-QTY-002 — received qty <= DC qty (requires corpus context, deferred to Phase 7)."""
    return CheckResult.skipped(
        "CHK-REF-QTY-002",
        "Cross-document check: requires corpus context (Phase 7)",
    )
