"""Evaluate real upload bundles through the product pipeline in isolated storage.

Run: python -m evaluation.product_reliability --manifest corpus.json --output report.json
A case contains id, cohort, batches (lists of relative file paths), and expected
(mapping from relative path to PASS/FAIL/INCOMPLETE/NEEDS_REVIEW/UNSUPPORTED).
The manifest also declares data_origin (real_holdout or synthetic) and sha256
(mapping each file path to its expected digest). No expected case is dropped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

VALID_STATUSES = {"PASS", "FAIL", "INCOMPLETE", "NEEDS_REVIEW", "UNSUPPORTED"}


def summarize(rows: list[dict], data_origin: str) -> dict:
    passes = [r for r in rows if r["actual"] == "PASS"]
    defects = [r for r in rows if r["expected"] == "FAIL"]
    false_passes = sum(r["expected"] != "PASS" for r in passes)
    # Exact one-sided 95% upper bound when zero false clearances were observed.
    upper = 1 - 0.05 ** (1 / len(passes)) if passes and not false_passes else None
    errors = sum(r["actual"] == "ERROR" for r in rows)
    return {
        "expected_documents": len(rows),
        "automatic_passes": len(passes),
        "false_clearances": false_passes,
        "false_clearance_rate": false_passes / len(passes) if passes else None,
        "false_clearance_upper_95_zero_errors": upper,
        "defective_documents": len(defects),
        "defects_automatically_passed": sum(r["actual"] == "PASS" for r in defects),
        "defect_recall": sum(r["actual"] == "FAIL" for r in defects) / len(defects)
        if defects
        else None,
        "abstentions": sum(r["actual"] not in {"PASS", "FAIL", "ERROR"} for r in rows),
        "errors": errors,
        "decision_accuracy": sum(r["actual"] == r["expected"] for r in rows) / len(rows)
        if rows
        else None,
        "release_gate_passed": bool(
            data_origin == "real_holdout"
            and len(passes) >= 300
            and defects
            and not false_passes
            and not errors
            and all(r["actual"] == r["expected"] for r in rows)
        ),
        "gate_scope": "Dataset gate only; operational recovery and pilot gates remain separate",
    }


def run(manifest_path: Path) -> dict:
    if "audit_v2.server" in sys.modules:
        raise RuntimeError("Run the evaluator in a fresh process to isolate application state")
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    origin = manifest.get("data_origin")
    if origin not in {"real_holdout", "synthetic"} or not manifest.get("cases"):
        raise ValueError("Declare data_origin and at least one labelled case")
    root = manifest_path.resolve().parent
    case_ids = [c["id"] for c in manifest["cases"]]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("Case IDs must be unique")
    # Validate the complete manifest before any model calls.
    for case in manifest["cases"]:
        files = [name for batch in case["batches"] for name in batch]
        if not files or set(files) != set(case["expected"]):
            raise ValueError(
                "Every uploaded file must have exactly one expected decision"
            )
        for name, status in case["expected"].items():
            path = (root / name).resolve()
            if not path.is_relative_to(root) or status not in VALID_STATUSES:
                raise ValueError("Invalid case path or expected status")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if manifest.get("sha256", {}).get(name) != digest:
                raise ValueError(f"Missing or mismatched source hash: {name}")
    rows = []
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="audit-evaluation-") as temporary:
        # Isolate all state before importing the real server pipeline.
        settings = {
            "V2_OPERATIONAL_DB": str(Path(temporary) / "operations.db"),
            "AUDIT_SESSION_DB": str(Path(temporary) / "sessions.db"),
            "V2_ARTIFACT_ROOT": str(Path(temporary) / "artifacts"),
            "V2_PERSISTENCE": "sqlite",
            "V2_JOB_BACKEND": "local",
            "V2_AUTO_CLEARANCE_ENABLED": "true",
        }
        previous = {key: os.environ.get(key) for key in settings}
        os.environ.update(settings)
        try:
            from audit_v2.pipeline.events import NullProgressSink
            from audit_v2.server import OPERATIONAL_STORE, _process_documents

            for case in manifest["cases"]:
                tenant = "evaluation-" + hashlib.sha256(case["id"].encode()).hexdigest()
                error = None
                try:
                    for batch in case["batches"]:
                        payload = [
                            (
                                name,
                                (root / name).read_bytes(),
                                mimetypes.guess_type(name)[0] or "application/pdf",
                            )
                            for name in batch
                        ]
                        _process_documents(payload, tenant, NullProgressSink())
                except Exception as exc:  # noqa: BLE001 - every failed case stays in the denominator
                    error = type(exc).__name__
                with OPERATIONAL_STORE.transaction(tenant) as tx:
                    state = tx.load() or {}
                results = {
                    r["document_name"]: r for r in state.get("results", {}).values()
                }
                for name, expected in case["expected"].items():
                    result = results.get(name, {})
                    rows.append(
                        {
                            "case_id": case["id"],
                            "cohort": case.get("cohort", "unspecified"),
                            "file": name,
                            "expected": expected,
                            "actual": "ERROR"
                            if error
                            else result.get("audit_status", "ERROR"),
                            "error": error,
                            "decision": result.get("decision"),
                        }
                    )
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    return {
        "schema_version": "product-eval-1",
        "created_at": datetime.now(UTC).isoformat(),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "data_origin": origin,
        "elapsed_seconds": time.monotonic() - started,
        "candidate_clearance_measured_with_release_switch_enabled": True,
        "overall": summarize(rows, origin),
        "cohorts": {
            cohort: summarize([r for r in rows if r["cohort"] == cohort], origin)
            for cohort in sorted({r["cohort"] for r in rows})
        },
        "documents": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["overall"]["release_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
