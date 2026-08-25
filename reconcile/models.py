"""Domain models for three-way reconciliation. All money is Decimal."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel

from audit_v2.domain.models import Severity


class PayoutRecord(BaseModel):
    txn_id: str
    payout_amount: Decimal
    payout_date: date
    settlement_status: str
    currency: str = "INR"


class BankEntry(BaseModel):
    bank_ref: str
    credited_amount: Decimal
    value_date: date
    counterparty: str | None = None
    currency: str = "INR"


class LedgerRecord(BaseModel):
    invoice_id: str
    expected_amount: Decimal
    due_date: date
    payer_id: str
    currency: str = "INR"


class MatchStatus(StrEnum):
    MATCHED = "MATCHED"
    EXCEPTION = "EXCEPTION"
    PARTIAL = "PARTIAL"


class ExceptionType(StrEnum):
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    MISSING_BANK_CREDIT = "MISSING_BANK_CREDIT"
    MISSING_LEDGER = "MISSING_LEDGER"
    DUPLICATE_TXN_ID = "DUPLICATE_TXN_ID"
    DATE_DRIFT = "DATE_DRIFT"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"


class MatchResult(BaseModel):
    txn_id: str
    status: MatchStatus
    payout: PayoutRecord | None = None
    bank: BankEntry | None = None
    ledger: LedgerRecord | None = None
    exception_type: ExceptionType | None = None
    risk_level: Severity | None = None
    amount_delta: Decimal | None = None
    date_drift_days: int | None = None
    decision_fingerprint: str
    llm_explanation: str | None = None


class ReconciliationRun(BaseModel):
    run_id: str
    run_at: datetime
    total: int  # payout rows processed; orphan bank credits are extra findings
    matched: int
    exceptions: int
    match_rate: Decimal
    unmatched_bank_credits: int = 0
    results: list[MatchResult]
    llm_summary: str | None = None
    #: "demo" when a schema-valid ground truth was supplied and checked, else "live"
    mode: str = "live"
    validation: ValidationReport | None = None
    mode_note: str | None = None


class ValidationReport(BaseModel):
    """Engine-vs-manifest agreement. Only exists when a truth file was supplied."""
    detected: int              # injected exception-type breaks the engine flagged
    total_breaks: int          # exception-type breaks in the manifest
    fee_matches_confirmed: int # AMOUNT_MISMATCH breaks matched within tolerance
    fee_total: int
    drift_matches_confirmed: int
    drift_total: int
    false_positives: list[str]
    false_negatives: list[str]
    passed: bool
