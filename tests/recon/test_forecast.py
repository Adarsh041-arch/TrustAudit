"""Forecast tests: weekly bucketing, lane classification, median lag."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from reconcile.forecast import DEFAULT_LAG_DAYS, derive_median_lag, project_cash
from reconcile.models import (
    BankEntry,
    ExceptionType,
    LedgerRecord,
    MatchResult,
    MatchStatus,
    PayoutRecord,
    ReconciliationRun,
)

AS_OF = date(2026, 8, 23)  # a Sunday


def _run(results: list[MatchResult]) -> ReconciliationRun:
    return ReconciliationRun(
        run_id="f", run_at=datetime.now(UTC), total=len(results), matched=0,
        exceptions=0, match_rate=Decimal(0), results=results,
    )


def result(txn="T1", *, payout_date=None, payout_amt=None, value_date=None,
           credited=None, due=date(2026, 9, 15), ledger_amt=Decimal(1000),
           status=MatchStatus.MATCHED, exc=None, drift=None):
    return MatchResult(
        txn_id=txn,
        status=status,
        payout=PayoutRecord(txn_id=txn, payout_amount=payout_amt or Decimal(1000),
                            payout_date=payout_date or date(2026, 7, 1),
                            settlement_status="ok") if payout_date else None,
        bank=BankEntry(bank_ref=f"BK{txn}", credited_amount=credited or Decimal(1000),
                       value_date=value_date or date(2026, 7, 5)) if value_date else None,
        ledger=LedgerRecord(invoice_id=txn, expected_amount=ledger_amt,
                            due_date=due, payer_id="P"),
        exception_type=exc,
        amount_delta=(payout_amt - credited) if (payout_amt and credited) else None,
        date_drift_days=drift,
        decision_fingerprint=f"sha256:{txn}",
        llm_explanation=None,
    )


def test_settled_money_lands_in_its_own_week():
    # Wed Jul 1 and Fri Jul 3 2026 are the same ISO week (Mon Jun 29)
    r = _run([
        result("A", value_date=date(2026, 7, 1)),
        result("B", value_date=date(2026, 7, 3)),
        result("C", value_date=date(2026, 7, 6)),  # next Monday -> new week
    ])
    fc = project_cash(r, as_of=AS_OF)
    assert len(fc.buckets) == 2
    assert fc.buckets[0].week_start == date(2026, 6, 29)
    assert fc.buckets[0].settled == Decimal(2000)
    assert fc.buckets[1].week_start == date(2026, 7, 6)
    assert fc.buckets[1].settled == Decimal(1000)


def test_missing_credit_after_eta_is_in_transit_before_as_of_at_risk():
    # eta = payout + lag; with lag 2: Jul 10 < as_of -> overdue -> at risk
    r = _run([result("M", payout_date=date(2026, 7, 8),
                     status=MatchStatus.EXCEPTION,
                     exc=ExceptionType.MISSING_BANK_CREDIT)])
    fc = project_cash(r, as_of=AS_OF)
    assert fc.at_risk_ids == ["M"]
    assert fc.totals.at_risk == Decimal(1000)

    # same row but payout recent -> in transit
    r2 = _run([result("M2", payout_date=AS_OF - timedelta(days=1),
                      status=MatchStatus.EXCEPTION,
                      exc=ExceptionType.MISSING_BANK_CREDIT)])
    fc2 = project_cash(r2, as_of=AS_OF)
    assert fc2.in_transit_ids == ["M2"]
    assert fc2.totals.in_transit == Decimal(1000)
    assert fc2.totals.at_risk == Decimal(0)


def test_clean_future_inflow_uses_due_date():
    r = _run([result("F", payout_date=None, due=date(2026, 9, 15))])
    fc = project_cash(r, as_of=AS_OF)
    week = fc.buckets[0]
    assert week.week_start == date(2026, 9, 14)  # Monday of that week
    assert week.expected == Decimal(1000) and week.settled == Decimal(0)


def test_median_lag_derived_and_fallback():
    rows = [
        result("A", payout_date=date(2026, 7, 1), value_date=date(2026, 7, 2), drift=1),
        result("B", payout_date=date(2026, 7, 1), value_date=date(2026, 7, 11), drift=10),
        result("C", payout_date=date(2026, 7, 1), value_date=date(2026, 7, 4), drift=3),
    ]
    assert derive_median_lag(rows) == (3, "derived")
    assert derive_median_lag([]) == (DEFAULT_LAG_DAYS, "fallback")


def test_duplicate_rows_counted_once():
    dup = result("D", value_date=date(2026, 7, 2))
    r = _run([
        dup,
        MatchResult(**{**dup.model_dump(), "exception_type": ExceptionType.DUPLICATE_TXN_ID,
                       "status": MatchStatus.EXCEPTION}),
    ])
    fc = project_cash(r, as_of=AS_OF)
    assert fc.totals.settled == Decimal(1000)


def test_orphans_skipped_empty_forecast_ok():
    orphan = MatchResult(txn_id="BKO", status=MatchStatus.EXCEPTION,
                         exception_type=ExceptionType.MISSING_LEDGER,
                         decision_fingerprint="sha256:x")
    fc = project_cash(_run([orphan]), as_of=AS_OF)
    assert fc.buckets == [] and fc.lag_source == "fallback"


def test_totals_sum_all_buckets():
    r = _run([
        result("A", value_date=date(2026, 7, 1)),
        result("F", payout_date=None, due=date(2026, 9, 15), ledger_amt=Decimal(500)),
    ])
    t = project_cash(r, as_of=AS_OF).totals
    assert t.settled == Decimal(1000) and t.expected == Decimal(500)
