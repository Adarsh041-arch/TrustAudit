"""Rollforward validators — CHK-RFWD-* checks."""
from decimal import Decimal
from typing import cast

from audit_v2.domain.models import CheckContext, CheckResult


def check_balance_roll_forward(ctx: CheckContext) -> CheckResult:
    """CHK-RFWD-BALANCE-001 — opening + receipts - payments = closing."""
    doc = ctx.document
    h = doc.header
    missing = []
    opening_raw = _decimal(h.opening_balance)
    receipts_raw = _decimal(h.receipts)
    payments_raw = _decimal(h.payments)
    closing_raw = _decimal(h.closing_balance)
    if opening_raw is None:
        missing.append("opening_balance")
    if receipts_raw is None:
        missing.append("receipts")
    if payments_raw is None:
        missing.append("payments")
    if closing_raw is None:
        missing.append("closing_balance")
    if missing:
        return CheckResult.skipped(
            "CHK-RFWD-BALANCE-001",
            f"Missing fields: {', '.join(missing)}",
        )
    opening = cast(Decimal, opening_raw)
    receipts = cast(Decimal, receipts_raw)
    payments = cast(Decimal, payments_raw)
    closing = cast(Decimal, closing_raw)
    expected = opening + receipts - payments
    delta = abs(expected - closing)
    if delta > ctx.tolerance_for("CHK-RFWD-BALANCE-001"):
        return CheckResult.failed(
            "CHK-RFWD-BALANCE-001",
            expected=str(expected),
            actual=str(closing),
            delta=str(delta),
            message=f"Opening {opening} + receipts {receipts} - payments {payments} "
                    f"= {expected}, stated closing {closing}",
        )
    return CheckResult.passed("CHK-RFWD-BALANCE-001")


def _decimal(pv) -> Decimal | None:
    if pv is None:
        return None
    try:
        return pv.decimal_value
    except Exception:
        return None
