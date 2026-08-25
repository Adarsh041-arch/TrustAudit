"""Classifier: pure rule table, no fixtures needed."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from audit_v2.domain.models import ToleranceSpec
from reconcile.classifier import classify
from reconcile.models import ExceptionType

TOL = ToleranceSpec(type="absolute", value="100")


def test_none_when_all_agree():
    from reconcile.models import BankEntry, LedgerRecord, PayoutRecord

    p = PayoutRecord(txn_id="T", payout_amount=Decimal(10), payout_date=date(2026, 1, 1),
                     settlement_status="ok")
    b = BankEntry(bank_ref="T", credited_amount=Decimal(10), value_date=date(2026, 1, 1))
    l = LedgerRecord(invoice_id="T", expected_amount=Decimal(10), due_date=date(2026, 2, 1),
                     payer_id="P")
    assert classify(p, b, l, Decimal(0), 0, TOL, 3) is None


def test_absence_branches():
    from reconcile.models import BankEntry, PayoutRecord

    p = PayoutRecord(txn_id="T", payout_amount=Decimal(10), payout_date=date(2026, 1, 1),
                     settlement_status="ok")
    b = BankEntry(bank_ref="T", credited_amount=Decimal(10), value_date=date(2026, 1, 1))

    assert classify(None, b, None, None, None, TOL, 3) is ExceptionType.MISSING_LEDGER
    assert classify(p, None, None, None, None, TOL, 3) is ExceptionType.MISSING_BANK_CREDIT


def test_delta_and_drift_branches():
    from reconcile.models import BankEntry, LedgerRecord, PayoutRecord

    def trio():
        p = PayoutRecord(txn_id="T", payout_amount=Decimal(10), payout_date=date(2026, 1, 1),
                         settlement_status="ok")
        b = BankEntry(bank_ref="T", credited_amount=Decimal(10), value_date=date(2026, 1, 1))
        l = LedgerRecord(invoice_id="T", expected_amount=Decimal(10), due_date=date(2026, 2, 1),
                         payer_id="P")
        return p, b, l

    big_delta = Decimal(-150)   # beyond Rs.100 fee band
    small_delta = Decimal(-50)
    assert classify(*trio(), big_delta, None, TOL, 3) is ExceptionType.AMOUNT_MISMATCH
    assert classify(*trio(), small_delta, None, TOL, 3) is None
    assert classify(*trio(), None, 5, TOL, 3) is ExceptionType.DATE_DRIFT
    assert classify(*trio(), None, 3, TOL, 3) is None
