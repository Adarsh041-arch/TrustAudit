#!/usr/bin/env python3
"""Measure V1 baseline metrics on the golden set.

Usage: python evaluation/measure_v1_baseline.py [--golden-set PATH]

Records precision, recall, latency, and cost per document
to evaluation/baselines/v1.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINES_DIR = REPO_ROOT / "evaluation" / "baselines"
SAMPLE_DOCS = REPO_ROOT / "sample_docs"
MANIFESTS_DIR = REPO_ROOT / "evaluation" / "golden_set" / "manifests"

import sys

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "evaluation"))

# Load .env so a real GOOGLE_API_KEY is visible before deciding on stubs.
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except Exception:
    pass

import os

# Offline shims replace the Gemini client with a canned stub. Installing them
# when a real key exists silently turns a "measured baseline" into stub output
# (this is exactly what invalidated the first committed baseline). Only stub
# when there is genuinely no key, or when --offline is passed explicitly.
_provider = os.getenv("LLM_PROVIDER", "google")
_KEY_VAR = {"nvidia": "NVIDIA_API_KEY", "ollama": None}.get(_provider, "GOOGLE_API_KEY")
_HAS_REAL_KEY = _KEY_VAR is None or bool(os.getenv(_KEY_VAR))
_OFFLINE = "--offline" in sys.argv
if _OFFLINE:
    _HAS_REAL_KEY = False
if not _HAS_REAL_KEY:
    try:
        from offline_shims import install_offline_shims
        install_offline_shims()
    except Exception:
        pass
    try:
        from stub_vlm import install_stub_if_no_key
        install_stub_if_no_key()
    except Exception:
        pass


@dataclass
class GoldenDoc:
    document_id: str
    doc_type: str
    source_path: Path
    expected: list[dict[str, Any]]


def _load_manifests() -> list[GoldenDoc]:
    if not MANIFESTS_DIR.is_dir():
        return []
    docs: list[GoldenDoc] = []
    for yaml_path in sorted(MANIFESTS_DIR.glob("*.yaml")):
        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}
        source = data.get("source", "")
        if not source:
            continue
        source_path = REPO_ROOT / source
        if not source_path.exists():
            source_path = SAMPLE_DOCS / Path(source).name
        if not source_path.exists():
            continue
        docs.append(GoldenDoc(
            document_id=data.get("document_id", yaml_path.stem),
            doc_type=data.get("doc_type", "unknown"),
            source_path=source_path,
            expected=data.get("expected_findings", []),
        ))
    return docs


def _run_v1_on_document(doc_path: Path, doc_type: str) -> dict[str, Any]:
    start = time.monotonic()
    error: str | None = None
    findings: list[dict[str, Any]] = []
    pages_processed = 0
    score = 0.0
    passed = False

    try:
        sys.path.insert(0, str(REPO_ROOT))

        from app.state import AuditState
        from app.graph import build_graph, parse_checklist_md
        from app.schemas import AuditChecklist
        from app.vlm import get_vlm_client as _real_get

        def _safe_get():
            try:
                return _real_get()
            except Exception:
                if _HAS_REAL_KEY:
                    # With a real key, a client failure is a measurement error,
                    # not a cue to silently substitute the stub.
                    raise
                from stub_vlm import StubVLMClient
                return StubVLMClient()

        import app.graph as _graph_mod
        _graph_mod.get_vlm_client = _safe_get

        checklist_path = REPO_ROOT / "checklist.md"
        checklist: AuditChecklist
        if checklist_path.is_file():
            checklist = parse_checklist_md(str(checklist_path))
        else:
            checklist = AuditChecklist(audit_name="Default", version="1.0", rules=[])

        # V1's upload_folder_node rescans uploaded_folder and overwrites
        # state.documents — pointing it at the shared golden-set dir would
        # audit all 200 docs per "single-doc" run. Isolate the doc in a
        # temp dir so the graph only sees the document under test.
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory(prefix="v1_baseline_") as tmp_dir:
            tmp_doc = Path(tmp_dir) / doc_path.name
            shutil.copyfile(doc_path, tmp_doc)

            state = AuditState(
                uploaded_folder=tmp_dir,
                documents=[str(tmp_doc)],
                document_summaries=[],
                audit_checklist=checklist,
                audit_results=[],
                processing_index=0,
            )

            graph = build_graph()
            result_state = graph.invoke(state)

        results = result_state.get("audit_results", []) or []
        if results:
            r = results[0]
            score = float(getattr(r, "score", 0.0) or 0.0)
            passed = bool(getattr(r, "passed", False))
            failed = getattr(r, "failed_rules", []) or []
            findings = [
                {"check_id": _infer_check_id(getattr(fr, "rule_id", "")),
                 "status": "FAIL"}
                for fr in failed
            ]

        try:
            import fitz
            with fitz.open(str(doc_path)) as pdf_doc:
                pages_processed = min(len(pdf_doc), 10)
        except Exception:
            pages_processed = 1

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    elapsed = time.monotonic() - start
    return {
        "document": doc_path.name,
        "doc_type": doc_type,
        "elapsed_seconds": round(elapsed, 4),
        "pages_processed": pages_processed,
        "findings": findings,
        "score": score,
        "passed": passed,
        "error": error,
    }


_RULE_ID_TO_CHECK: dict[str, str] = {
    "R003": "CHK-ARITH-LINE-001",
    "R001": "CHK-FORMAT-MANDATORY-001",
    "R002": "CHK-ARITH-SUBTOTAL-001",
    "R004": "CHK-ARITH-TAX-001",
    "R005": "CHK-ARITH-TAX-002",
    "R006": "CHK-ARITH-GRAND-001",
    "R007": "CHK-FORMAT-WORDS-001",
    "R008": "CHK-DUP-CORPUS-001",
    "R009": "CHK-REF-GST-001",
}


def _infer_check_id(rule_id: str) -> str:
    rid = rule_id.upper().strip()
    if rid in _RULE_ID_TO_CHECK:
        return _RULE_ID_TO_CHECK[rid]
    if rid.startswith("CHK-"):
        return rid
    return rid


def _score_against_gold(
    expected: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> dict[str, float]:
    expected_fails = {e["check_id"] for e in expected if e.get("expected_status") == "FAIL"}
    reported_fails = {f["check_id"] for f in findings if f.get("status") == "FAIL"}

    if not expected_fails and not reported_fails:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 0, "fp": 0, "fn": 0}

    tp = len(expected_fails & reported_fails)
    fp = len(reported_fails - expected_fails)
    fn = len(expected_fails - reported_fails)

    precision = tp / (tp + fp) if (tp + fp) > 0 else (1.0 if not reported_fails else 0.0)
    recall = tp / (tp + fn) if (tp + fn) > 0 else (1.0 if not expected_fails else 0.0)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure V1 baseline on golden set")
    parser.add_argument(
        "--golden-set",
        type=Path,
        default=SAMPLE_DOCS,
        help="Directory containing golden set documents",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BASELINES_DIR / "v1.json",
        help="Output path for baseline JSON",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Measure at most N documents (real model calls cost money)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force stub VLM (no model calls); baseline is labeled measurement_mode=stub",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Concurrent documents (each doc is an independent graph run)",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    manifests = _load_manifests()
    if args.limit:
        manifests = manifests[: args.limit]
    if not manifests:
        print(f"WARNING: no manifests found in {MANIFESTS_DIR}", file=sys.stderr)
        baseline = {
            "version": "1",
            "measured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "documents_count": 0,
            "documents_successful": 0,
            "average_latency_seconds": 0.0,
            "metrics": {
                "overall_precision": 0.0,
                "overall_recall": 0.0,
                "overall_f1": 0.0,
                "estimated_cost_per_doc_inr": 0.0,
            },
            "per_document": [],
            "golden_set_source": "evaluation/golden_set/manifests",
            "gate": "M0 - Phase 0 V1 baseline",
        }
        with open(args.output, "w") as f:
            json.dump(baseline, f, indent=2)
        return

    def _measure(gd: GoldenDoc) -> dict[str, Any]:
        print(f"  Measuring V1 on {gd.source_path.name} ...", file=sys.stderr)
        run = _run_v1_on_document(gd.source_path, gd.doc_type)
        scoring = _score_against_gold(gd.expected, run["findings"])
        return {
            "document": gd.source_path.name,
            "document_id_gold": gd.document_id,
            "doc_type": gd.doc_type,
            "elapsed_seconds": run["elapsed_seconds"],
            "pages_processed": run["pages_processed"],
            "expected_fail_check_ids": sorted(
                {e["check_id"] for e in gd.expected if e.get("expected_status") == "FAIL"}
            ),
            "reported_fail_check_ids": sorted(
                f["check_id"] for f in run["findings"] if f.get("status") == "FAIL"
            ),
            "findings_count": len(run["findings"]),
            "passed": run["passed"],
            "score": run["score"],
            "precision": scoring["precision"],
            "recall": scoring["recall"],
            "f1": scoring["f1"],
            "tp": scoring["tp"],
            "fp": scoring["fp"],
            "fn": scoring["fn"],
            "estimated_cost_inr": round(run["elapsed_seconds"] * 0.5, 4),
            "error": run["error"],
        }

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = list(pool.map(_measure, manifests))

    successful = sum(1 for r in results if r["error"] is None)
    avg_latency = (
        sum(r["elapsed_seconds"] for r in results) / len(results) if results else 0.0
    )
    scored = [r for r in results if r["error"] is None]
    if scored:
        macro_p = sum(r["precision"] for r in scored) / len(scored)
        macro_r = sum(r["recall"] for r in scored) / len(scored)
        macro_f1 = sum(r["f1"] for r in scored) / len(scored)
    else:
        macro_p = macro_r = macro_f1 = 0.0

    baseline = {
        "version": "1",
        "measured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "measurement_mode": "real_model" if _HAS_REAL_KEY else "stub",
        "provider": _provider if _HAS_REAL_KEY else "stub",
        "model": (
            os.getenv(
                "GEMINI_MODEL",
                "google/diffusiongemma-26b-a4b-it" if _provider == "nvidia" else "gemini-2.5-flash",
            )
            if _HAS_REAL_KEY
            else "stub_vlm"
        ),
        "corpus_note": "synthetic golden set (evaluation/golden_set), no real scanned documents",
        "documents_count": len(results),
        "documents_successful": successful,
        "average_latency_seconds": round(avg_latency, 4),
        "metrics": {
            "overall_precision": round(macro_p, 4),
            "overall_recall": round(macro_r, 4),
            "overall_f1": round(macro_f1, 4),
            "estimated_cost_per_doc_inr": round(avg_latency * 0.5, 4),
        },
        "per_document": results,
        "golden_set_source": "evaluation/golden_set/manifests",
        "gate": "M0 - Phase 0 V1 baseline (precision/recall vs. expected_findings)",
        "notes": (
            "V1 delegates arithmetic to the LLM (B1 defect) and uses float math "
            "(B3 defect). This baseline establishes the floor that V2 must beat."
        ),
    }

    with open(args.output, "w") as f:
        json.dump(baseline, f, indent=2)

    print(f"\nBaseline written to {args.output}", file=sys.stderr)
    print(
        f"Documents: {baseline['documents_count']} ({baseline['documents_successful']} successful)",
        file=sys.stderr,
    )
    print(
        f"Macro P/R/F1: {baseline['metrics']['overall_precision']:.4f} / "
        f"{baseline['metrics']['overall_recall']:.4f} / "
        f"{baseline['metrics']['overall_f1']:.4f}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
