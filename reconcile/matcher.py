"""Deterministic three-way join: payouts x bank credits x ledger expectations.

No model calls. Verdicts and the match rate come only from this module.
"""
from __future__ import annotations

import hashlib
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from audit_v2.domain.models import Severity, ToleranceSpec
from reconcile.classifier import classify
from reconcile.models import (
    BankEntry,
    ExceptionType,
    LedgerRecord,
    MatchResult,
    MatchStatus,
    PayoutRecord,
    ReconciliationRun,
)

RULESET_VERSION = "recon-rules-1.0.0"

#: Gateway/settlement fees up to Rs.100 are tolerated as MATCHED (delta recorded).
FEE_TOLERANCE = ToleranceSpec(type="absolute", value="100")
#: Bank value_date may lag the payout date by at most this many days.
DATE_TOLERANCE_DAYS = 3
#: Exceptions at or above this exposure bump one risk level.
MATERIALITY_THRESHOLD = Decimal(500000)

_RISK_BASE: dict[ExceptionType, Severity] = {
    ExceptionType.MISSING_BANK_CREDIT: Severity.HIGH,
    ExceptionType.MISSING_LEDGER: Severity.HIGH,
    ExceptionType.CURRENCY_MISMATCH: Severity.MEDIUM,
    ExceptionType.AMOUNT_MISMATCH: Severity.MEDIUM,
    ExceptionType.DATE_DRIFT: Severity.LOW,
    ExceptionType.DUPLICATE_TXN_ID: Severity.LOW,
}
_LADDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


def assess_risk(r: MatchResult) -> Severity:
    """Deterministic severity: base by exception type, bumped by materiality."""
    base = _RISK_BASE.get(r.exception_type, Severity.MEDIUM)
    amount = (
        (r.bank.credited_amount if r.bank else None)
        or (r.payout.payout_amount if r.payout else None)
        or (r.ledger.expected_amount if r.ledger else None)
        or Decimal(0)
    )
    if base is not Severity.CRITICAL and amount >= MATERIALITY_THRESHOLD:
        return _LADDER[min(_LADDER.index(base) + 1, len(_LADDER) - 1)]
    return base


def compute_fingerprint(
    txn_id: str,
    payout_amount: Decimal,
    credited_amount: Decimal | None,
    value_date,
) -> str:
    raw = f"{RULESET_VERSION}|{txn_id}|{payout_amount}|{credited_amount}|{value_date}"
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"


def _find_bank(bank_by_ref: dict[str, list[BankEntry]], txn_id: str) -> BankEntry | None:
    candidates = bank_by_ref.get(txn_id)
    if not candidates and txn_id.upper().startswith("TXN"):
        candidates = bank_by_ref.get(f"BK{txn_id[3:]}")
    return candidates.pop(0) if candidates else None


def reconcile(
    payouts: list[PayoutRecord],
    bank_entries: list[BankEntry],
    ledger_records: list[LedgerRecord],
    *,
    fee_tolerance: ToleranceSpec = FEE_TOLERANCE,
    max_drift_days: int = DATE_TOLERANCE_DAYS,
    run_id: str | None = None,
) -> ReconciliationRun:
    bank_by_ref: dict[str, list[BankEntry]] = defaultdict(list)
    for b in bank_entries:
        bank_by_ref[b.bank_ref].append(b)
    ledger_by_id = {l.invoice_id: l for l in ledger_records}

    occurrences: Counter[str] = Counter()
    results: list[MatchResult] = []
    claimed_refs: set[str] = set()

    for p in payouts:
        occurrences[p.txn_id] += 1
        fingerprint = compute_fingerprint(p.txn_id, p.payout_amount, None, p.payout_date)

        if occurrences[p.txn_id] > 1:
            results.append(MatchResult(
                txn_id=p.txn_id, status=MatchStatus.EXCEPTION, payout=p,
                exception_type=ExceptionType.DUPLICATE_TXN_ID,
                decision_fingerprint=fingerprint,
            ))
            continue

        bank = _find_bank(bank_by_ref, p.txn_id)
        if bank is not None:
            claimed_refs.add(bank.bank_ref)
        ledger = ledger_by_id.get(p.txn_id)

        delta = p.payout_amount - bank.credited_amount if bank else None
        drift = (bank.value_date - p.payout_date).days if bank else None
        exc_type = classify(p, bank, ledger, delta, drift, fee_tolerance, max_drift_days)

        if exc_type is not None:
            status = MatchStatus.EXCEPTION
        elif ledger is None:
            status = MatchStatus.PARTIAL  # payout + bank agree, no ledger counterpart
        else:
            status = MatchStatus.MATCHED

        results.append(MatchResult(
            txn_id=p.txn_id, status=status, payout=p, bank=bank, ledger=ledger,
            exception_type=exc_type, amount_delta=delta, date_drift_days=drift,
            decision_fingerprint=compute_fingerprint(
                p.txn_id, p.payout_amount,
                bank.credited_amount if bank else None,
                bank.value_date if bank else p.payout_date,
            ),
        ))

    # Bank credits nobody claimed: money in the bank with no payout/ledger behind it.
    orphan_count = 0
    for b in bank_entries:
        if b.bank_ref in claimed_refs:
            continue
        orphan_count += 1
        results.append(MatchResult(
            txn_id=b.bank_ref, status=MatchStatus.EXCEPTION, bank=b,
            exception_type=ExceptionType.MISSING_LEDGER,
            decision_fingerprint=compute_fingerprint(b.bank_ref, b.credited_amount, b.credited_amount, b.value_date),
        ))

    for r in results:
        if r.exception_type is not None:
            r.risk_level = assess_risk(r)

    matched = sum(r.status is MatchStatus.MATCHED for r in results if r.payout is not None)
    total = len(payouts)
    return ReconciliationRun(
        run_id=run_id or uuid.uuid4().hex[:12],
        run_at=datetime.now(UTC),
        total=total,
        matched=matched,
        exceptions=sum(r.status is MatchStatus.EXCEPTION for r in results),
        match_rate=(Decimal(matched) / Decimal(total)).quantize(Decimal("0.0001")),
        unmatched_bank_credits=orphan_count,
        results=results,
    )
