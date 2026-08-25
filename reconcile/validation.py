"""Ground-truth validation: engine verdicts vs an injected-break manifest.

Runs are "demo" mode when a schema-valid truth file accompanies the uploads;
"live" otherwise. A malformed truth file never crashes a run and never
produces a fabricated accuracy number - it is rejected with a reason.
"""
from __future__ import annotations

import json
from typing import Any

from reconcile.models import (
    ExceptionType,
    MatchStatus,
    ReconciliationRun,
    ValidationReport,
)

_KNOWN_BREAK_TYPES = {
    "AMOUNT_MISMATCH",        # tolerated fee -> must MATCH with recorded delta
    "MISSING_BANK_CREDIT",
    "CURRENCY_MISMATCH",
    "DATE_DRIFT_TOLERATED",   # within drift window -> must MATCH
    "DUPLICATE_TXN_ID",
    "ORPHAN_BANK_CREDIT",     # manifests as MISSING_LEDGER exception
}
_EXPECTED_EXCEPTION_TYPES = {"MISSING_BANK_CREDIT", "CURRENCY_MISMATCH", "DUPLICATE_TXN_ID"}
_TRUTH_SOURCE_TYPES = {"MISSING_BANK_CREDIT", "CURRENCY_MISMATCH", "DUPLICATE_TXN_ID", "ORPHAN_BANK_CREDIT"}


def parse_ground_truth(raw: bytes) -> dict[str, Any]:
    """Schema-check raw truth-file bytes. Raises ValueError on anything off."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ValueError(f"not valid JSON ({err})") from None
    if not isinstance(data, dict):
        raise ValueError("top level must be a JSON object")  # noqa: TRY004 - single error type for callers
    if not isinstance(data.get("total_records"), int) or data["total_records"] <= 0:
        raise ValueError("'total_records' must be a positive integer")
    breaks = data.get("breaks")
    if not isinstance(breaks, list):
        raise ValueError("'breaks' must be a list")  # noqa: TRY004
    for i, brk in enumerate(breaks):
        if not isinstance(brk, dict) or not isinstance(brk.get("txn_id"), str) or not brk["txn_id"]:
            raise ValueError(f"breaks[{i}] needs a non-empty string 'txn_id'")
        if brk.get("type") not in _KNOWN_BREAK_TYPES:
            raise ValueError(f"breaks[{i}] has unknown type {brk.get('type')!r}")
    return data


def validate_run(run: ReconciliationRun, truth: dict[str, Any]) -> ValidationReport:
    """Compare engine output to the manifest. Numbers are computed here -
    an 'expected' block inside the truth file is never trusted."""
    breaks = truth["breaks"]
    by_type: dict[str, list[dict]] = {}
    for b in breaks:
        by_type.setdefault(b["type"], []).append(b)

    flagged = {r.txn_id for r in run.results if r.status is MatchStatus.EXCEPTION}

    detected = sum(1 for b in breaks if b["type"] in _TRUTH_SOURCE_TYPES and b["txn_id"] in flagged)

    def confirmed(kind: str) -> int:
        ok = 0
        for b in by_type.get(kind, []):
            r = next((x for x in run.results if x.txn_id == b["txn_id"]), None)
            if kind == "AMOUNT_MISMATCH":
                if r is not None and r.status is MatchStatus.MATCHED and r.amount_delta:
                    ok += 1
            elif kind == "DATE_DRIFT_TOLERATED":
                max_days = truth.get("tolerances", {}).get("max_drift_days", 3)
                if r is not None and r.status is MatchStatus.MATCHED \
                        and r.date_drift_days is not None and abs(r.date_drift_days) <= max_days:
                    ok += 1
        return ok

    fee_conf = confirmed("AMOUNT_MISMATCH")
    drift_conf = confirmed("DATE_DRIFT_TOLERATED")

    false_negatives = sorted(
        b["txn_id"] for b in breaks
        if b["type"] in _EXPECTED_EXCEPTION_TYPES and b["txn_id"] not in flagged
    )
    orphan_ids = {b["txn_id"] for b in by_type.get("ORPHAN_BANK_CREDIT", [])}
    false_negatives += sorted(
        rid for rid in orphan_ids
        if rid not in {r.txn_id for r in run.results
                       if r.exception_type is ExceptionType.MISSING_LEDGER}
    )
    all_manifest_ids = {b["txn_id"] for b in breaks}
    false_positives = sorted(flagged - all_manifest_ids)

    return ValidationReport(
        detected=detected,
        total_breaks=len([b for b in breaks if b["type"] in _TRUTH_SOURCE_TYPES]),
        fee_matches_confirmed=fee_conf,
        fee_total=len(by_type.get("AMOUNT_MISMATCH", [])),
        drift_matches_confirmed=drift_conf,
        drift_total=len(by_type.get("DATE_DRIFT_TOLERATED", [])),
        false_positives=false_positives,
        false_negatives=sorted(set(false_negatives)),
        passed=not false_positives and not false_negatives
        and detected == len([b for b in breaks if b["type"] in _TRUTH_SOURCE_TYPES]),
    )
