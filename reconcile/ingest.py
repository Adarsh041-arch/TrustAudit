"""CSV ingestion: parse the three source files into typed records.

Bad rows raise ValueError with file+line context - never silently skipped.
Accepts filesystem paths or open binary file objects (uploads).
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO

from reconcile.models import BankEntry, LedgerRecord, PayoutRecord

Source = str | Path | BinaryIO


def _rows(source: Source) -> list[tuple[int, dict]]:
    if hasattr(source, "read"):
        text = source.read().decode("utf-8-sig")
        reader = csv.DictReader(text.splitlines())
        rows = list(reader)
    else:
        with open(source, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    if reader.fieldnames is None:
        raise ValueError(f"{getattr(source, 'name', source)}: empty or headerless CSV")
    return [(i, row) for i, row in enumerate(rows, start=2)]


def _decimal(path: Source, line: int, field: str, raw: str) -> Decimal:
    try:
        return Decimal(raw.strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{path}:{line}: {field}={raw!r} is not a valid amount") from None


def _date(path: Source, line: int, field: str, raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except (ValueError, AttributeError):
        raise ValueError(f"{path}:{line}: {field}={raw!r} is not an ISO date") from None


def _required(row: dict, field: str, path: Source, line: int) -> str:
    value = (row.get(field) or "").strip()
    if not value:
        raise ValueError(f"{path}:{line}: missing required field {field!r}")
    return value


def load_payouts(path: Source) -> list[PayoutRecord]:
    return [
        PayoutRecord(
            txn_id=_required(row, "txn_id", path, line),
            payout_amount=_decimal(path, line, "payout_amount", row.get("payout_amount", "")),
            payout_date=_date(path, line, "payout_date", row.get("payout_date", "")),
            settlement_status=(row.get("settlement_status") or "").strip(),
            currency=(row.get("currency") or "INR").strip(),
        )
        for line, row in _rows(path)
    ]


def load_bank(path: Source) -> list[BankEntry]:
    return [
        BankEntry(
            bank_ref=_required(row, "bank_ref", path, line),
            credited_amount=_decimal(path, line, "credited_amount", row.get("credited_amount", "")),
            value_date=_date(path, line, "value_date", row.get("value_date", "")),
            counterparty=(row.get("counterparty") or "").strip() or None,
            currency=(row.get("currency") or "INR").strip(),
        )
        for line, row in _rows(path)
    ]


def load_ledger(path: Source) -> list[LedgerRecord]:
    return [
        LedgerRecord(
            invoice_id=_required(row, "invoice_id", path, line),
            expected_amount=_decimal(path, line, "expected_amount", row.get("expected_amount", "")),
            due_date=_date(path, line, "due_date", row.get("due_date", "")),
            payer_id=_required(row, "payer_id", path, line),
            currency=(row.get("currency") or "INR").strip(),
        )
        for line, row in _rows(path)
    ]

