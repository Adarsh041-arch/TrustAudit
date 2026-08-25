"""Deterministic cash forecasting over reconciliation results.

Projects expected inflows from the ledger, adjusted by what the recon engine
already proved about each transaction. No model calls - every number here is
Decimal arithmetic over verdicts.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from statistics import median

from pydantic import BaseModel, Field

from reconcile.models import ExceptionType, MatchResult, MatchStatus, ReconciliationRun

#: Settlement-lag fallback when matched history is too thin to derive one.
DEFAULT_LAG_DAYS = 2


class ForecastBucket(BaseModel):
    week_start: date  # Monday of the ISO week
    settled: Decimal = Decimal(0)     # bank credit received on/before as_of
    in_transit: Decimal = Decimal(0)  # payout issued, credit projected after as_of
    expected: Decimal = Decimal(0)    # clean future inflow
    at_risk: Decimal = Decimal(0)     # overdue/unresolvable inflows

    @property
    def total(self) -> Decimal:
        return self.settled + self.in_transit + self.expected + self.at_risk


class CashForecast(BaseModel):
    as_of: date
    median_lag_days: int
    lag_source: str  # "derived" | "fallback"
    buckets: list[ForecastBucket] = Field(default_factory=list)
    in_transit_ids: list[str] = Field(default_factory=list)
    at_risk_ids: list[str] = Field(default_factory=list)
    llm_summary: str | None = None

    @property
    def totals(self) -> ForecastBucket:
        t = ForecastBucket(week_start=self.as_of)
        for b in self.buckets:
            t.settled += b.settled
            t.in_transit += b.in_transit
            t.expected += b.expected
            t.at_risk += b.at_risk
        return t


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def derive_median_lag(results: list[MatchResult]) -> tuple[int, str]:
    """Median payout->credit lag over matched rows; fallback when too thin."""
    lags = [
        r.date_drift_days
        for r in results
        if r.date_drift_days is not None and r.date_drift_days >= 0
        and r.bank is not None and r.payout is not None
    ]
    if lags:
        return int(median(lags)), "derived"
    return DEFAULT_LAG_DAYS, "fallback"


def project_cash(run: ReconciliationRun, as_of: date | None = None) -> CashForecast:
    """Project cash position by ISO week from verdicts already computed."""
    as_of = as_of or datetime.now(UTC).date()
    lag_days, lag_source = derive_median_lag(run.results)
    forecast = CashForecast(as_of=as_of, median_lag_days=lag_days, lag_source=lag_source)

    by_week: dict[date, ForecastBucket] = {}

    def bucket(d: date) -> ForecastBucket:
        ws = _week_start(d)
        return by_week.setdefault(ws, ForecastBucket(week_start=ws))

    seen_txn: set[str] = set()

    for r in run.results:
        if r.ledger is None or r.txn_id in seen_txn:
            continue  # duplicates/orphans carry no distinct expected money
        seen_txn.add(r.txn_id)

        if r.bank is not None:
            if r.bank.value_date <= as_of:
                bucket(r.bank.value_date).settled += r.bank.credited_amount
            else:
                bucket(r.bank.value_date).expected += r.bank.credited_amount
            continue

        # No bank credit. What we project depends on why.
        eta = (
            r.payout.payout_date + timedelta(days=max(lag_days, 0))
            if r.payout else r.ledger.due_date
        )
        if r.exception_type is ExceptionType.MISSING_BANK_CREDIT and eta > as_of:
            bucket(eta).in_transit += r.payout.payout_amount  # type: ignore[union-attr]
            forecast.in_transit_ids.append(r.txn_id)
        elif r.status is MatchStatus.EXCEPTION:
            bucket(max(eta, r.ledger.due_date)).at_risk += r.ledger.expected_amount
            forecast.at_risk_ids.append(r.txn_id)
        else:
            bucket(max(eta, r.ledger.due_date)).expected += r.ledger.expected_amount

    forecast.buckets = sorted(by_week.values(), key=lambda b: b.week_start)
    return forecast
