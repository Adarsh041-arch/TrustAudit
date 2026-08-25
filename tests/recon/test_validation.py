"""Ground-truth gating: schema checks, demo/live mode, no fabricated numbers."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from reconcile.validation import parse_ground_truth, validate_run

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "generate_recon_batch.py"


@pytest.fixture(scope="module")
def batch(tmp_path_factory):
    out = tmp_path_factory.mktemp("val_batch")
    subprocess.run(
        [sys.executable, str(GENERATOR), "--records", "100", "--seed", "42", "--out", str(out)],
        check=True,
    )
    return out


def _truth(batch: Path) -> dict:
    return json.loads((batch / "recon_ground_truth.json").read_text())


def _run_reconcile(batch: Path):
    from reconcile.ingest import load_bank, load_ledger, load_payouts
    from reconcile.matcher import reconcile

    return reconcile(
        load_payouts(batch / "payout_report.csv"),
        load_bank(batch / "bank_statement.csv"),
        load_ledger(batch / "ledger.csv"),
    )


def test_parse_accepts_generated_truth(batch):
    truth = parse_ground_truth((batch / "recon_ground_truth.json").read_bytes())
    assert truth["total_records"] == 100
    assert len(truth["breaks"]) == 16


@pytest.mark.parametrize("mutate, why", [
    (lambda d: {}, "empty object"),
    (lambda d: {**d, "total_records": "many"}, "bad total_records type"),
    (lambda d: {**d, "breaks": None}, "breaks not a list"),
    (lambda d: {**d, "breaks": [{"txn_id": ""}]}, "empty txn_id"),
    (lambda d: {**d, "breaks": [{"txn_id": "X", "type": "SOMETHING_ELSE"}]}, "unknown break type"),
])
def test_parse_rejects_malformed_truth(batch, mutate, why):
    raw = json.dumps(mutate(_truth(batch))).encode()
    with pytest.raises(ValueError):
        parse_ground_truth(raw)


def test_parse_rejects_non_json():
    with pytest.raises(ValueError):
        parse_ground_truth(b"payout_report.csv,771256\x00")


def test_validate_full_agreement_on_seeded_batch(batch):
    v = validate_run(_run_reconcile(batch), _truth(batch))
    assert (v.detected, v.total_breaks) == (8, 8)
    assert (v.fee_matches_confirmed, v.fee_total) == (5, 5)
    assert (v.drift_matches_confirmed, v.drift_total) == (3, 3)
    assert v.false_positives == [] and v.false_negatives == []
    assert v.passed is True


def test_tampered_truth_yields_false_negatives_not_crash(batch):
    truth = _truth(batch)
    for b in truth["breaks"]:
        if b["type"] == "MISSING_BANK_CREDIT":
            b["txn_id"] = "TXN9999"  # engine will never find this
            break
    v = validate_run(_run_reconcile(batch), truth)
    assert "TXN9999" in v.false_negatives
    assert v.passed is False


def test_engine_defaults_to_live_mode(batch):
    run = _run_reconcile(batch)
    assert run.mode == "live" and run.validation is None
