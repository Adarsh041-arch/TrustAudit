#!/usr/bin/env python3
"""Measure V2 against the golden set — §6 evaluation harness.

Runs `AuditWorkflow` over every generated golden document, compares emitted
findings against the gold manifests, and reports per-category precision /
recall / F1, extraction field F1, and the §6 gate table.

Scoring model (per document, per routed check):
- gold FAIL + emitted FAIL  -> TP
- gold FAIL + emitted PASS  -> FN  (missed defect)
- gold PASS/absent + FAIL   -> FP  (false alarm — kills reviewer trust)
- gold PASS/absent + PASS   -> TN
SKIPPED / NEEDS_REVIEW emissions are counted separately, not as verdicts.

Usage:
  python evaluation/measure_v2.py                       # full run
  python evaluation/measure_v2.py --limit 20            # quick pass
  python evaluation/measure_v2.py --out evaluation/baselines/v2.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from audit_v2.ingestion.document_store import MemoryDocumentStore
from audit_v2.orchestration.workflows import (
    AuditWorkflow,
    AuditWorkflowInput,
)
from evaluation.metrics import ConfusionMatrix, aggregate_metrics

DOCS_DIR = REPO_ROOT / "evaluation" / "golden_set" / "docs"
MANIFESTS_DIR = REPO_ROOT / "evaluation" / "golden_set" / "manifests"

CATEGORY_OF_PREFIX = {
    "CHK-ARITH": "arithmetic",
    "CHK-RFWD": "rollforward",
    "CHK-SEQ": "sequence",
    "CHK-THRESHOLD": "threshold",
    "CHK-TEMP": "temporal",
    "CHK-REF": "reference_integrity",
    "CHK-FORMAT": "format_completeness",
}


def category_of(check_id: str) -> str:
    for prefix, cat in CATEGORY_OF_PREFIX.items():
        if check_id.startswith(prefix):
            return cat
    return "other"


def load_manifests(limit: int | None = None) -> list[dict]:
    manifests = []
    for path in sorted(MANIFESTS_DIR.glob("*_gold.yaml")):
        with open(path, encoding="utf-8") as f:
            m = yaml.safe_load(f)
        # Only score generator-v2 manifests: they carry expected_fields/lines.
        if m.get("generator_version", "").startswith("2."):
            manifests.append(m)
    if limit:
        manifests = manifests[:limit]
    return manifests


async def run_document(manifest: dict) -> dict | None:
    pdf_path = REPO_ROOT / manifest["source"]
    if not pdf_path.exists():
        return None
    data = pdf_path.read_bytes()

    store = MemoryDocumentStore()
    workflow = AuditWorkflow(store=store)
    record = store.create(
        tenant_id="golden",
        content_hash="sha256:golden",
        source_uri=f"golden://{pdf_path.name}",
    )
    out = await workflow.run(AuditWorkflowInput(
        document_id=record.document_id,
        tenant_id="golden",
        ruleset_version="rs_2026_07_26",
        data=data,
        mime_type="application/pdf",
        file_size=len(data),
    ))
    return {
        "status": out.status,
        "error": out.error,
        "findings": [
            {"check_id": f.check_id, "status": f.status.value
             if hasattr(f.status, "value") else str(f.status)}
            for f in out.findings
        ],
        "document": out.document.model_dump() if out.document else None,
    }


def score_findings(
    manifest: dict, result: dict, matrices: dict[str, ConfusionMatrix],
    misses: list[dict], false_alarms: list[dict],
) -> None:
    gold_fails = {
        ef["check_id"] for ef in manifest.get("expected_findings", [])
        if ef.get("expected_status") == "FAIL"
    }
    emitted: dict[str, str] = {}
    for f in result["findings"]:
        # A check emits one finding per document in the current runner.
        emitted[f["check_id"]] = f["status"]

    for check_id, status in emitted.items():
        cat = category_of(check_id)
        m = matrices[cat]
        if status not in ("PASS", "FAIL"):
            continue  # SKIPPED / NEEDS_REVIEW are not verdicts
        if check_id in gold_fails:
            if status == "FAIL":
                m.tp += 1
            else:
                m.fn += 1
                misses.append({
                    "document_id": manifest["document_id"],
                    "check_id": check_id,
                    "defects": manifest.get("defects", []),
                })
        else:
            if status == "FAIL":
                m.fp += 1
                false_alarms.append({
                    "document_id": manifest["document_id"],
                    "check_id": check_id,
                    "defects": manifest.get("defects", []),
                })
            else:
                m.tn += 1

    # Gold FAILs the pipeline never emitted a verdict for are misses too.
    for check_id in gold_fails - set(emitted):
        matrices[category_of(check_id)].fn += 1
        misses.append({
            "document_id": manifest["document_id"],
            "check_id": check_id,
            "defects": manifest.get("defects", []),
            "note": "no finding emitted",
        })


def _decimal_equal(a: str, b: str, tolerance: str | None = None) -> bool:
    if a is None or b is None:
        return a == b
    try:
        da = Decimal(a.replace(",", ""))
        db = Decimal(b.replace(",", ""))
        if tolerance:
            return abs(da - db) <= Decimal(tolerance)
        return da == db
    except Exception:
        return a.strip().casefold() == b.strip().casefold()


def score_extraction(manifest: dict, result: dict, field_stats: dict) -> None:
    doc = result.get("document")
    if doc is None:
        return
    header = doc.get("header", {})
    gold_fields = manifest.get("expected_fields", {})
    gold_lines = manifest.get("expected_lines", [])

    for field_key, gold_value in gold_fields.items():
        extracted = header.get(field_key)
        extracted_str = ""
        if isinstance(extracted, dict):
            extracted_str = extracted.get("text", extracted.get("decimal_value", "")) or ""
        elif extracted is not None:
            extracted_str = str(extracted)

        match = _decimal_equal(extracted_str, str(gold_value)) if gold_value is not None else (extracted is None)
        field_stats.setdefault(field_key, {"tp": 0, "fp": 0, "fn": 0})
        if match:
            field_stats[field_key]["tp"] += 1
        else:
            field_stats[field_key]["fn"] += 1
            if extracted_str:
                field_stats[field_key]["fp"] += 1

    extracted_lines = doc.get("line_items", [])
    gold_tuples = {(l["qty"], l["rate"], l["total"], l.get("hsn", ""))
                   for l in gold_lines}
    ext_tuples = {(l.get("qty", ""), l.get("rate", ""), l.get("total", ""),
                   l.get("hsn", "")) for l in extracted_lines}
    line_matches = len(gold_tuples & ext_tuples)
    field_stats.setdefault("lines", {"tp": 0, "fp": 0, "fn": 0})
    field_stats["lines"]["tp"] += line_matches
    field_stats["lines"]["fn"] += len(gold_tuples) - line_matches
    field_stats["lines"]["fp"] += len(ext_tuples) - line_matches


async def main_async(args: argparse.Namespace) -> dict:
    manifests = load_manifests(args.limit)
    if not manifests:
        print("No generator-2.x gold manifests found. "
              "Run evaluation/golden_set/generator.py first.")
        sys.exit(1)

    matrices: dict[str, ConfusionMatrix] = defaultdict(ConfusionMatrix)
    misses: list[dict] = []
    false_alarms: list[dict] = []
    statuses: dict[str, int] = defaultdict(int)
    errors: list[dict] = []
    field_stats: dict = {}

    for i, manifest in enumerate(manifests, 1):
        result = await run_document(manifest)
        if result is None:
            errors.append({"document_id": manifest["document_id"],
                           "error": "source PDF missing"})
            continue
        statuses[result["status"]] += 1
        if result["error"]:
            errors.append({"document_id": manifest["document_id"],
                           "error": result["error"]})
            continue
        score_findings(manifest, result, matrices, misses, false_alarms)
        score_extraction(manifest, result, field_stats)
        if args.verbose and i % 25 == 0:
            print(f"  ... {i}/{len(manifests)}")

    report = aggregate_metrics(dict(matrices))
    report["documents"] = len(manifests)
    report["statuses"] = dict(statuses)
    report["errors"] = errors
    report["misses"] = misses
    report["false_alarms"] = false_alarms

    def _compute_f1(tp: int, fp: int, fn: int) -> float:
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        return 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

    total_tp = sum(v["tp"] for v in field_stats.values())
    total_fp = sum(v["fp"] for v in field_stats.values())
    total_fn = sum(v["fn"] for v in field_stats.values())
    report["extraction"] = {
        "f1": round(_compute_f1(total_tp, total_fp, total_fn), 4),
        "tp": total_tp,
        "fp": total_fp,
        "fn": total_fn,
        "fields": field_stats,
    }

    arith = report["per_category"].get("arithmetic", {})
    report["gates"] = {
        "arithmetic_precision": {
            "value": arith.get("precision"), "target": 1.00,
            "pass": arith.get("precision") == 1.0,
        },
        "arithmetic_recall": {
            "value": arith.get("recall"), "target": 0.98,
            "pass": (arith.get("recall") or 0) >= 0.98,
        },
        "overall_precision": {
            "value": report["overall"]["precision"], "target": 0.90,
            "pass": report["overall"]["precision"] >= 0.90,
        },
        "overall_recall": {
            "value": report["overall"]["recall"], "target": 0.85,
            "pass": report["overall"]["recall"] >= 0.85,
        },
        "extraction_f1": {
            "value": round(report["extraction"]["f1"], 4) if report.get("extraction") else 0.0,
            "target": 0.95,
            "pass": (report.get("extraction", {}).get("f1") or 0) >= 0.95,
        },
    }
    return report


def print_report(report: dict) -> None:
    print(f"\nDocuments scored: {report['documents']}")
    print(f"Statuses: {report['statuses']}")
    if report["errors"]:
        print(f"Errors: {len(report['errors'])}")
        for e in report["errors"][:5]:
            print(f"  {e}")

    print("\nPer-category metrics:")
    hdr = f"{'category':<22}{'prec':>8}{'recall':>8}{'f1':>8}{'tp':>6}{'fp':>6}{'fn':>6}{'tn':>6}"
    print(hdr)
    print("-" * len(hdr))
    for cat, m in sorted(report["per_category"].items()):
        print(f"{cat:<22}{m['precision']:>8.4f}{m['recall']:>8.4f}{m['f1']:>8.4f}"
              f"{m['tp']:>6}{m['fp']:>6}{m['fn']:>6}{m['tn']:>6}")
    o = report["overall"]
    print(f"{'OVERALL':<22}{o['precision']:>8.4f}{o['recall']:>8.4f}{o['f1']:>8.4f}")

    print("\nGates:")
    for name, g in report["gates"].items():
        mark = "PASS" if g["pass"] else "FAIL"
        print(f"  [{mark}] {name}: {g['value']} (target {g['target']})")

    if report.get("extraction"):
        print(f"\nExtraction field F1: {report['extraction']['f1']:.4f}"
              f"  (TP={report['extraction']['tp']}, "
              f"FP={report['extraction']['fp']}, "
              f"FN={report['extraction']['fn']})")

    if report["misses"]:
        print(f"\nMissed defects ({len(report['misses'])}):")
        for miss in report["misses"][:15]:
            print(f"  {miss}")
    if report["false_alarms"]:
        print(f"\nFalse alarms ({len(report['false_alarms'])}):")
        for fa in report["false_alarms"][:15]:
            print(f"  {fa}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure V2 against the golden set")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    report = asyncio.run(main_async(args))
    print_report(report)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        # Keep the JSON artifact small and stable: drop per-doc TN noise.
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nReport written to {args.out}")

    all_pass = all(g["pass"] for g in report["gates"].values())
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
