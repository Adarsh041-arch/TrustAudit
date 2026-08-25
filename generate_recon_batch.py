#!/usr/bin/env python3
"""Synthetic three-way reconciliation batch generator.

Emits payout_report.csv, bank_statement.csv, ledger.csv plus
recon_ground_truth.json recording every injected break.

Usage:
  python generate_recon_batch.py --records 100 --seed 42 --out data/recon/

Break layout over N payout rows (N=100 default):
  5  AMOUNT_MISMATCH      bank credited Rs.25-100 short (fee) -> MATCHED within tolerance
  3  MISSING_BANK_CREDIT  payout exists, no bank row          -> EXCEPTION
  3  DATE_DRIFT           value_date 1-3 days after payout    -> MATCHED within drift window
  1  CURRENCY_MISMATCH    ledger row in USD                   -> EXCEPTION
  2  DUPLICATE_TXN_ID     txn_id appears twice in payout file -> copy flagged EXCEPTION
  2  ORPHAN_BANK_CREDIT   bank credit with no payout/ledger   -> MISSING_LEDGER (extra findings,
                              not part of the payout denominator)

Expected at defaults: 94/100 matched (94%). Without the fee tolerance band:
89/100 (89%) - that delta is the demo's failure-recovery story.
"""

import argparse
import csv
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

BASE_DATE = date(2026, 7, 1)
COUNTERPARTIES = [
    "Acme Logistics Pvt Ltd", "Brightline Media", "Corewave Systems",
    "Delta Freight Carriers", "Everest Supplies", "Finch Analytics",
]
BREAK_COUNTS = {
    "fee": 5, "missing": 3, "drift": 3, "currency": 1, "dup_pairs": 2, "orphans": 2,
}
FEE_MIN, FEE_MAX = Decimal("25.00"), Decimal("100.00")


def _money(lo: int, hi: int, rng: random.Random) -> Decimal:
    return Decimal(rng.randint(lo * 100, hi * 100)) / Decimal(100)


def build_batch(n_records: int, seed: int) -> tuple[list[dict], list[dict], list[dict], dict]:
    rng = random.Random(seed)
    need = sum(BREAK_COUNTS.values())
    if n_records < need * 4:
        raise SystemExit(f"--records must be >= {need * 4} to fit all injected breaks")

    order = list(range(n_records))
    rng.shuffle(order)
    it = iter(order)
    fee_idx = {next(it) for _ in range(BREAK_COUNTS["fee"])}
    missing_idx = {next(it) for _ in range(BREAK_COUNTS["missing"])}
    drift_idx = {next(it) for _ in range(BREAK_COUNTS["drift"])}
    currency_idx = next(it)
    # dup: target keeps its identity (matched); source becomes a stray repeat of it
    dup_targets = [next(it) for _ in range(BREAK_COUNTS["dup_pairs"])]
    dup_sources = [next(it) for _ in range(BREAK_COUNTS["dup_pairs"])]

    payouts: list[dict] = []
    bank_rows: list[dict] = []
    ledger_rows: list[dict] = []
    breaks: list[dict] = []
    statuses: list[str] = []

    for i in range(n_records):
        if i in dup_sources:
            statuses.append("")  # filled after its target exists
            payouts.append(None)  # placeholder, replaced below
            continue

        txn_id = f"TXN{1000 + i}"
        payout_date = BASE_DATE + timedelta(days=i % 60)
        amount = _money(10_000, 900_000, rng)
        counterparty = COUNTERPARTIES[i % len(COUNTERPARTIES)]

        status = "CLEAN"
        credited_amount, value_date, bank_currency = amount, payout_date, "INR"
        ledger_amount, ledger_currency = amount, "INR"

        if i in fee_idx:
            fee = Decimal(rng.randint(int(FEE_MIN * 100), int(FEE_MAX * 100))) / Decimal(100)
            credited_amount = amount - fee
            status = "FEE_MATCH"
            breaks.append({"txn_id": txn_id, "type": "AMOUNT_MISMATCH",
                           "delta": str(-fee), "reason": "processing_fee"})
        elif i in missing_idx:
            status = "MISSING_BANK"
            breaks.append({"txn_id": txn_id, "type": "MISSING_BANK_CREDIT"})
        elif i in drift_idx:
            drift_days = rng.randint(1, 3)
            value_date = payout_date + timedelta(days=drift_days)
            status = "DRIFT_MATCH"
            breaks.append({"txn_id": txn_id, "type": "DATE_DRIFT_TOLERATED",
                           "days": drift_days})
        elif i == currency_idx:
            ledger_currency = "USD"
            status = "CURRENCY"
            breaks.append({"txn_id": txn_id, "type": "CURRENCY_MISMATCH",
                           "ledger_currency": "USD"})

        payouts.append({
            "txn_id": txn_id,
            "payout_amount": f"{amount:.2f}",
            "payout_date": payout_date.isoformat(),
            "settlement_status": "processed",
            "currency": "INR",
        })
        statuses.append(status)

        if status != "MISSING_BANK":
            bank_rows.append({
                "bank_ref": f"BK{txn_id[3:]}",
                "credited_amount": f"{credited_amount:.2f}",
                "value_date": value_date.isoformat(),
                "counterparty": counterparty,
                "currency": bank_currency,
            })
        ledger_rows.append({
            "invoice_id": txn_id,
            "expected_amount": f"{ledger_amount:.2f}",
            "due_date": (payout_date + timedelta(days=30)).isoformat(),
            "payer_id": f"PAYER{100 + (i % 20)}",
            "currency": ledger_currency,
        })

    # Duplicate rows: source rows become repeats of their targets.
    for src_i, tgt_i in zip(dup_sources, dup_targets):
        dup_row = dict(payouts[tgt_i])
        payouts[src_i] = dup_row
        statuses[src_i] = "DUP_COPY"
        statuses[tgt_i] = "DUP_ORIG"
        breaks.append({"txn_id": dup_row["txn_id"], "type": "DUPLICATE_TXN_ID"})

    # Orphan bank credits: no payout, no ledger.
    for o in range(BREAK_COUNTS["orphans"]):
        ref = f"BKORPHAN{101 + o}"
        bank_rows.append({
            "bank_ref": ref,
            "credited_amount": f"{_money(50_000, 200_000, rng):.2f}",
            "value_date": (BASE_DATE + timedelta(days=rng.randint(0, 59))).isoformat(),
            "counterparty": "Unknown Remitter",
            "currency": "INR",
        })
        breaks.append({"txn_id": ref, "type": "ORPHAN_BANK_CREDIT"})

    matched = sum(s in {"CLEAN", "FEE_MATCH", "DRIFT_MATCH", "DUP_ORIG"} for s in statuses)
    truth = {
        "total_records": n_records,
        "clean_matches": sum(s == "CLEAN" for s in statuses),
        "seed": seed,
        "tolerances": {"fee_absolute": str(FEE_MAX), "max_drift_days": 3},
        "breaks": breaks,
        "expected": {
            "matched_payouts": matched,
            "exception_payouts": n_records - matched,
            "orphan_bank_credits": BREAK_COUNTS["orphans"],
            "match_rate": str(Decimal(matched) / Decimal(n_records)),
        },
    }
    return payouts, bank_rows, ledger_rows, truth


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic recon batch")
    parser.add_argument("--records", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/recon")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payouts, bank, ledger, truth = build_batch(args.records, args.seed)

    write_csv(out / "payout_report.csv", payouts)
    write_csv(out / "bank_statement.csv", bank)
    write_csv(out / "ledger.csv", ledger)
    (out / "recon_ground_truth.json").write_text(json.dumps(truth, indent=2))

    exp = truth["expected"]
    print(f"Generated batch of {args.records} (seed={args.seed}) -> {out}/")
    print(f"  payout_report.csv : {len(payouts)} rows")
    print(f"  bank_statement.csv: {len(bank)} rows")
    print(f"  ledger.csv        : {len(ledger)} rows")
    print(f"  expected match rate: {exp['matched_payouts']}/{args.records} "
          f"({Decimal(exp['match_rate']) * 100:.0f}%)")


if __name__ == "__main__":
    main()
