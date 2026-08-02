"""Rollforward validators — CHK-RFWD-* checks."""
from decimal import Decimal

from audit_v2.domain.models import CheckContext, CheckResult, ProvenancedValue


def check_balance_roll_forward(ctx: CheckContext) -> CheckResult:
    """CHK-RFWD-BALANCE-001 — opening + receipts - payments = closing."""
    doc = ctx.document
    header = doc.header
    opening = _decimal(header.opening_balance)
    closing = _decimal(header.closing_balance)
    receipts = _decimal(header.receipts)
    payments = _decimal(header.payments)

    missing = []
    if opening is None:
        missing.append("opening_balance")
    if receipts is None:
        missing.append("receipts")
    if payments is None:
        missing.append("payments")
    if closing is None:
        missing.append("closing_balance")

    if missing:
        return CheckResult.skipped(
            "CHK-RFWD-BALANCE-001",
            f"Missing fields: {', '.join(missing)}",
        )


    assert opening is not None and closing is not None
    assert receipts is not None and payments is not None

    expected = opening + receipts - payments
    delta = abs(closing - expected)
    tolerance = ctx.tolerance_for("CHK-RFWD-BALANCE-001")

    if delta > tolerance:
        return CheckResult.failed(
            "CHK-RFWD-BALANCE-001",
            expected=str(expected),
            actual=str(closing),
            delta=str(delta),
            message=f"Opening {opening} + receipts {receipts} - payments {payments} "
                    f"= {expected}, stated closing {closing}",
        )
    return CheckResult.passed("CHK-RFWD-BALANCE-001")


def _decimal(pv: ProvenancedValue | None) -> Decimal | None:
    if pv is None:
        return None
    try:
        return pv.decimal_value
    except Exception:
        return None

