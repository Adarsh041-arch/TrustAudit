"""Deterministic exception classification. Pure rules - no model calls."""
from __future__ import annotations

from decimal import Decimal

from audit_v2.domain.models import ToleranceSpec
from reconcile.models import BankEntry, ExceptionType, LedgerRecord, PayoutRecord


def classify(
    payout: PayoutRecord | None,
    bank: BankEntry | None,
    ledger: LedgerRecord | None,
    amount_delta: Decimal | None,
    drift_days: int | None,
    fee_tolerance: ToleranceSpec,
    max_drift_days: int,
) -> ExceptionType | None:
    """Assign the exception type from what is present/absent in the match attempt.

    Returns None when the three sources agree within tolerance.
    """
    if payout is None:
        return ExceptionType.MISSING_LEDGER  # bank credit with no payout behind it
    if bank is None:
        return ExceptionType.MISSING_BANK_CREDIT
    if payout.currency != bank.currency or (
        ledger is not None and ledger.currency != bank.currency
    ):
        return ExceptionType.CURRENCY_MISMATCH
    if drift_days is not None and drift_days > max_drift_days:
        return ExceptionType.DATE_DRIFT
    if amount_delta is not None and abs(amount_delta) > fee_tolerance.apply(payout.payout_amount):
        return ExceptionType.AMOUNT_MISMATCH
    return None
