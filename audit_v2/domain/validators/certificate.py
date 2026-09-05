"""Deterministic checks for certificates of origin."""
from audit_v2.domain.models import CheckContext, CheckResult
from audit_v2.extraction.parser import validate_hsn


def check_certificate_mandatory(ctx: CheckContext) -> CheckResult:
    required = (
        "certificate_number", "certificate_date", "exporter_name", "consignee_name",
    )
    missing = [name for name in required if getattr(ctx.document.header, name) is None]
    if not ctx.document.certificate_goods:
        missing.append("goods")
    if missing:
        return CheckResult.failed(
            "CHK-CERT-MANDATORY-001", "certificate identity, parties, and goods",
            f"missing: {', '.join(missing)}", "N/A",
            message=f"Certificate is missing required field(s): {', '.join(missing)}",
        )
    return CheckResult.passed("CHK-CERT-MANDATORY-001")


def check_certificate_goods(ctx: CheckContext) -> CheckResult:
    for row in ctx.document.certificate_goods:
        missing = [
            name for name in ("description", "hs_code", "quantity")
            if getattr(row, name) is None
        ]
        if missing:
            return CheckResult.failed(
                "CHK-CERT-GOODS-001", "description, HS code, and quantity",
                f"row {row.line_number} missing: {', '.join(missing)}", "N/A",
                message=f"Certificate goods row {row.line_number} is incomplete",
            )
        if not validate_hsn(row.hs_code.value):
            return CheckResult.failed(
                "CHK-CERT-GOODS-001", "4-8 digit HS code", row.hs_code.value, "N/A",
                message=f"Certificate goods row {row.line_number} has an invalid HS code",
            )
    return CheckResult.passed("CHK-CERT-GOODS-001")


def check_certificate_invoice_reference(ctx: CheckContext) -> CheckResult:
    header = ctx.document.header
    if header.referenced_invoice_number is None or header.referenced_invoice_date is None:
        return CheckResult.failed(
            "CHK-CERT-REFERENCE-001", "invoice number and invoice date", "missing", "N/A",
            message="Certificate does not contain a complete invoice reference",
        )
    return CheckResult.passed("CHK-CERT-REFERENCE-001")
