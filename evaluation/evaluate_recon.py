#!/usr/bin/env python3
"""Ground-truth validation harness for the recon engine.

Usage:
  python evaluation/evaluate_recon.py --batch data/recon/ \
      [--truth data/recon/recon_ground_truth.json]

Compares engine verdicts against the injected-break manifest (shared logic with
the API's demo-mode validation - reconcile/validation.py) and prints an honest
scorecard. Exit 0 = full agreement.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from reconcile.ingest import load_bank, load_ledger, load_payouts
from reconcile.matcher import reconcile
from reconcile.validation import parse_ground_truth, validate_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate recon engine against ground truth")
    parser.add_argument("--batch", required=True, help="directory with the 3 generated CSVs")
    parser.add_argument("--truth", help="ground truth JSON (default: <batch>/recon_ground_truth.json)")
    args = parser.parse_args()

    batch = Path(args.batch)
    truth_path = Path(args.truth) if args.truth else batch / "recon_ground_truth.json"
    try:
        truth = parse_ground_truth(truth_path.read_bytes())
    except ValueError as err:
        print(f"Ground truth REJECTED ({err}) - no accuracy claim can be made.")
        return 2

    run = reconcile(
        load_payouts(batch / "payout_report.csv"),
        load_bank(batch / "bank_statement.csv"),
        load_ledger(batch / "ledger.csv"),
    )
    v = validate_run(run, truth)

    print(f"Engine MATCHED:   {run.matched}/{run.total} ({run.match_rate * 100}%)")
    print("Mode:             DEMO - schema-valid ground truth accepted")
    print(f"Breaks detected:  {v.detected}/{v.total_breaks}")
    print(f"Fee-tolerance matches confirmed: {v.fee_matches_confirmed}/{v.fee_total}")
    print(f"Drift-tolerated matches confirmed: {v.drift_matches_confirmed}/{v.drift_total}")
    print(f"False positives:  {len(v.false_positives)}"
          + (f" {v.false_positives}" if v.false_positives else ""))
    print(f"False negatives:  {len(v.false_negatives)}"
          + (f" {v.false_negatives}" if v.false_negatives else ""))

    ok = v.passed
    print(f"\nVERDICT: {'PASS - 100% agreement with ground truth' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
