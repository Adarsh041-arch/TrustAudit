"""Matcher unit tests: deterministic verdicts over hand-built fixtures."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from reconcile.matcher import DATE_TOLERANCE_DAYS, FEE_TOLERANCE, reconcile
from reconcile.models import (
    BankEntry,
    ExceptionType,
    LedgerRecord,
    MatchStatus,
    PayoutRecord,
)

AMOUNT = Decimal("5000.00")


def payout(txn_id="TXN1", amount=AMOUNT, day=1):
    return PayoutRecord(
        txn_id=txn_id, payout_amount=amount,
        payout_date=date(2026, 7, day), settlement_status="processed",
    )


def bank(ref="TXN1", amount=AMOUNT, day=1):
    return BankEntry(bank_ref=ref, credited_amount=amount, value_date=date(2026, 7, day))


def ledger(invoice_id="TXN1", amount=AMOUNT, currency="INR"):
    return LedgerRecord(
        invoice_id=invoice_id, expected_amount=amount,
        due_date=date(2026, 8, 30), payer_id="PAYER1", currency=currency,
    )


def test_exact_match():
    run = reconcile([payout()], [bank()], [ledger()])
    r = run.results[0]
    assert r.status is MatchStatus.MATCHED
    assert run.matched == 1 and run.match_rate == Decimal("1.0000")


def test_fee_within_tolerance_is_matched():
    run = reconcile([payout(amount=Decimal("5000.00"))],
                    [bank(amount=Decimal("4950.00"))], [ledger()])
    r = run.results[0]
    assert r.status is MatchStatus.MATCHED
    assert r.amount_delta == Decimal("50.00")


def test_amount_over_tolerance_is_exception():
    run = reconcile([payout(amount=Decimal("5000.00"))],
                    [bank(amount=Decimal("4800.00"))], [ledger()])
    r = run.results[0]
    assert r.status is MatchStatus.EXCEPTION
    assert r.exception_type is ExceptionType.AMOUNT_MISMATCH


def test_missing_bank_credit():
    run = reconcile([payout()], [], [ledger()])
    r = run.results[0]
    assert r.exception_type is ExceptionType.MISSING_BANK_CREDIT
    assert run.matched == 0


def test_duplicate_txn_id_flags_second_occurrence():
    run = reconcile([payout(), payout()], [bank()], [ledger()])
    dupes = [r for r in run.results if r.exception_type is ExceptionType.DUPLICATE_TXN_ID]
    assert len(dupes) == 1
    matched = [r for r in run.results if r.status is MatchStatus.MATCHED]
    assert len(matched) == 1


def test_drift_within_window_matched():
    run = reconcile([payout(day=1)], [bank(day=3)], [ledger()])
    r = run.results[0]
    assert r.status is MatchStatus.MATCHED and r.date_drift_days == 2


def test_drift_beyond_window_is_exception():
    run = reconcile([payout(day=1)],
                    [bank(day=1 + DATE_TOLERANCE_DAYS + 1)], [ledger()])
    r = run.results[0]
    assert r.exception_type is ExceptionType.DATE_DRIFT


def test_currency_mismatch():
    run = reconcile([payout()], [bank()], [ledger(currency="USD")])
    assert run.results[0].exception_type is ExceptionType.CURRENCY_MISMATCH


def test_orphan_bank_credit_reported():
    orphan = BankEntry(bank_ref="BKORPHAN9", credited_amount=Decimal("1234.00"),
                       value_date=date(2026, 7, 5))
    run = reconcile([payout()], [bank(), orphan], [ledger()])
    orphans = [r for r in run.results if r.txn_id == "BKORPHAN9"]
    assert orphans[0].exception_type is ExceptionType.MISSING_LEDGER
    assert run.unmatched_bank_credits == 1
    # orphan must not dilute the payout-row match rate
    assert run.total == 1 and run.match_rate == Decimal("1.0000")


def test_missing_ledger_is_partial_not_exception():
    run = reconcile([payout()], [bank()], [])
    r = run.results[0]
    assert r.status is MatchStatus.PARTIAL and r.exception_type is None


def test_fingerprint_stable_and_sensitive():
    a = reconcile([payout()], [bank()], [ledger()]).results[0].decision_fingerprint
    b = reconcile([payout()], [bank()], [ledger()]).results[0].decision_fingerprint
    c = reconcile([payout(amount=AMOUNT + 1)], [bank(amount=AMOUNT + 1)], [ledger()]).results[0].decision_fingerprint
    assert a == b and a != c
    assert all(f.startswith("sha256:") for f in (a, b, c))


def test_risk_levels_assigned_by_type_and_materiality():
    from audit_v2.domain.models import Severity
    from reconcile.matcher import MATERIALITY_THRESHOLD

    # duplicate copy (no sources) -> LOW
    run = reconcile([payout(), payout()], [bank()], [ledger()])
    dup = next(r for r in run.results if r.exception_type is ExceptionType.DUPLICATE_TXN_ID)
    assert dup.risk_level is Severity.LOW

    # missing bank on a small payout -> HIGH; huge payout -> bumped to CRITICAL
    small = reconcile([payout("S", amount=Decimal(5000))], [], [ledger()])
    assert small.results[0].risk_level is Severity.HIGH

    big_amt = MATERIALITY_THRESHOLD + Decimal(1)
    big = reconcile([payout("B", amount=big_amt)], [],
                    [ledger(amount=big_amt)])
    assert big.results[0].risk_level is Severity.CRITICAL

    # matched rows carry no risk level
    ok = reconcile([payout()], [bank()], [ledger()])
    assert ok.results[0].risk_level is None


def test_fee_tolerance_spec_shape():
    assert FEE_TOLERANCE.type == "absolute"
    assert FEE_TOLERANCE.as_decimal() == Decimal(100)
