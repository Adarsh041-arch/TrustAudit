"""Full-batch ground truth validation: engine verdicts vs injected breaks.

This is the pitch-defense test - proves the 94% is honest.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from reconcile.ingest import load_bank, load_ledger, load_payouts
from reconcile.matcher import reconcile

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "generate_recon_batch.py"


@pytest.fixture(scope="module")
def batch_and_truth(tmp_path_factory):
    out = tmp_path_factory.mktemp("recon_batch")
    subprocess.run(
        [sys.executable, str(GENERATOR), "--records", "100", "--seed", "42",
         "--out", str(out)],
        check=True,
    )
    truth = json.loads((out / "recon_ground_truth.json").read_text())
    run = reconcile(
        load_payouts(out / "payout_report.csv"),
        load_bank(out / "bank_statement.csv"),
        load_ledger(out / "ledger.csv"),
    )
    return run, truth


def test_match_rate_matches_ground_truth(batch_and_truth):
    run, truth = batch_and_truth
    exp = truth["expected"]
    assert run.total == truth["total_records"]
    assert run.matched == exp["matched_payouts"]
    assert run.match_rate == Decimal(exp["match_rate"])
    assert run.unmatched_bank_credits == exp["orphan_bank_credits"]


def test_every_injected_break_is_found(batch_and_truth):
    run, truth = batch_and_truth
    found = Counter()
    for r in run.results:
        if r.exception_type is not None:
            found[str(r.exception_type)] += 1

    for brk in truth["breaks"]:
        match brk["type"]:
            case "AMOUNT_MISMATCH":
                # tolerated fee: matched with recorded delta, not an exception
                r = next(r for r in run.results if r.txn_id == brk["txn_id"])
                assert r.status.value == "MATCHED" and r.amount_delta is not None
            case "MISSING_BANK_CREDIT" | "CURRENCY_MISMATCH":
                r = next(r for r in run.results if r.txn_id == brk["txn_id"])
                assert r.exception_type is not None
                found[brk["type"]] -= 1
            case "DATE_DRIFT_TOLERATED":
                r = next(r for r in run.results if r.txn_id == brk["txn_id"])
                assert r.status.value == "MATCHED"
                assert abs(r.date_drift_days) <= truth["tolerances"]["max_drift_days"]
            case "DUPLICATE_TXN_ID":
                dupes = [r for r in run.results if r.txn_id == brk["txn_id"]]
                assert len(dupes) == 2
                found["DUPLICATE_TXN_ID"] -= 1
            case "ORPHAN_BANK_CREDIT":
                r = next(r for r in run.results if r.txn_id == brk["txn_id"])
                assert r.exception_type.value == "MISSING_LEDGER"

    # every counted exception type was accounted for by the manifest
    leftovers = {k: v for k, v in found.items() if k in
                 {"MISSING_BANK_CREDIT", "CURRENCY_MISMATCH", "DUPLICATE_TXN_ID"}}
    assert all(v == 0 for v in leftovers.values()), leftovers


def test_false_positive_free_on_clean_rows(batch_and_truth):
    """Rows with no injected break must never be flagged."""
    run, truth = batch_and_truth
    broken_ids = {b["txn_id"] for b in truth["breaks"]}
    clean_flagged = [
        r.txn_id for r in run.results
        if r.exception_type is not None and r.txn_id not in broken_ids
    ]
    assert clean_flagged == [], clean_flagged


def test_engine_is_deterministic(batch_and_truth, tmp_path_factory):
    """Same inputs -> same verdicts and fingerprints (PHASES_V2 §3.6)."""
    _, _ = batch_and_truth
    out = tmp_path_factory.mktemp("recon_batch_rerun")
    subprocess.run(
        [sys.executable, str(GENERATOR), "--records", "100", "--seed", "42",
         "--out", str(out)],
        check=True,
    )
    rerun = reconcile(
        load_payouts(out / "payout_report.csv"),
        load_bank(out / "bank_statement.csv"),
        load_ledger(out / "ledger.csv"),
    )
    first = batch_and_truth[0]
    assert [(r.txn_id, r.status.value, r.decision_fingerprint) for r in first.results] == \
           [(r.txn_id, r.status.value, r.decision_fingerprint) for r in rerun.results]
