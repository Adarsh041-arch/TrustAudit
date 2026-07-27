# M2.4 — §6 Harness Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire extraction F1 scoring, ECE calibration, and determinism measurement into `evaluation/measure_v2.py`.

**Architecture:** Three additive changes: (1) pipe `ExtractedDocument` through `AuditWorkflowOutput`, (2) implement `score_extraction()` to compare against golden manifest `expected_fields`/`expected_lines`, (3) call `compute_ece()` + `determinism_score()` from the main loop.

**Tech Stack:** Python 3.11, pytest, Audit V2 domain models, golden set YAML manifests.

## Global Constraints

- All monetary values: `Decimal` in code, strings in JSON/YAML.
- `compute_ece()` and `determinism_score()` already exist in `evaluation/metrics.py` — do not re-implement.
- Extraction scorer must handle missing fields (None/absent) without crashing.
- No new dependencies.

---

### Task 1: Expose `ExtractedDocument` from `AuditWorkflowOutput`

**Files:**
- Modify: `audit_v2/orchestration/workflows.py`
- No new tests needed (existing golden-set test will still pass).

**Interfaces:**
- Consumes: `ExtractedDocument` (already populated inside `run()`)
- Produces: `AuditWorkflowOutput.document: ExtractedDocument | None`

- [ ] **Step 1: Add document field to `AuditWorkflowOutput`**

In `workflows.py`, add to `AuditWorkflowOutput`:
```python
document: ExtractedDocument | None = None
```

- [ ] **Step 2: Populate it on the success path**

In `AuditWorkflow.run()`, after `run_checks_and_emit(...)` returns, set the document before returning:
```python
document=inp.document  # or wherever the normalized document lives
```

Find where the normalized document is available in `run()` — it's the `normalized` variable from `normalize_document(extraction.document)` in the Temporal workflow, and similarly in the plain workflow.

In `audit_v2/orchestration/workflows.py`, around line 194 (after `run_checks_and_emit`), add:
```python
document=normalized,
```
to the returned `AuditWorkflowOutput`.

- [ ] **Step 3: Verify existing tests still pass**

Run: `pytest tests/ -x --ignore=test_nvidia.py --ignore=test_litert.py --ignore=tests/chaos`
Expected: 328 passed

---

### Task 2: Implement `score_extraction()` in `measure_v2.py`

**Files:**
- Modify: `evaluation/measure_v2.py`

**Interfaces:**
- Consumes: `manifest["expected_fields"]` (dict[str, str]), `manifest["expected_lines"]` (list[dict]), `result["document"]` (ExtractedDocument)
- Produces: `field_stats` dict with per-field TP/FP/FN, overall extraction F1

- [ ] **Step 1: Write helper `_decimal_equal(a: str, b: str, tolerance: str | None = None) -> bool`**

```python
from decimal import Decimal

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
        return a.strip() == b.strip()
```

- [ ] **Step 2: Write `score_extraction()` body**

Replace the current no-op body. Logic:

```python
def score_extraction(manifest: dict, result: dict, field_stats: dict) -> None:
    """Compare extracted fields against golden manifest."""
    doc = result.get("document")
    if doc is None or not manifest.get("expected_fields"):
        return
    header = doc.get("header", {})
    gold_fields = manifest["expected_fields"]
    gold_lines = manifest.get("expected_lines", [])

    for field_key, gold_value in gold_fields.items():
        # Map manifest key to header attribute
        extracted = header.get(field_key)
        extracted_str = extracted.get("text") if isinstance(extracted, dict) else str(extracted or "")
        match = _decimal_equal(extracted_str, gold_value)
        field_stats.setdefault(field_key, {"tp": 0, "fp": 0, "fn": 0})
        if match:
            field_stats[field_key]["tp"] += 1
        else:
            field_stats[field_key]["fn"] += 1
            # Also FP if extracted something wrong
            if extracted and extracted_str:
                field_stats[field_key]["fp"] += 1

    # Line-item scoring: compare (qty, rate, total, hsn) tuples
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
```

- [ ] **Step 3: Pipe document through `run_document()`**

Modify `run_document()` to return the full `ExtractedDocument` dict alongside findings. Add to the return dict:
```python
"document": out.document.model_dump() if out.document else None,
```

- [ ] **Step 4: Wire into main loop**

In `main_async()`, add after `score_findings()`:
```python
field_stats: dict = {}
...
score_extraction(manifest, result, field_stats)
```
Then compute extraction F1 at the end:
```python
ext_f1 = ...
report["extraction"] = ext_f1
```

- [ ] **Step 5: Print extraction metrics**

In `print_report()`, add a section:
```python
if report.get("extraction"):
    print(f"\nExtraction field F1: {report['extraction']['f1']:.4f}")
```

---

### Task 3: Wire ECE and determinism

**Files:**
- Modify: `evaluation/measure_v2.py`

**Interfaces:**
- Consumes: `compute_ece(confidences, correct, n_bins=10)`, `determinism_score(run1_verdicts, run2_verdicts)`
- Produces: report entries for `ece` and `determinism`

- [ ] **Step 1: Collect confidence + correctness data during scoring pass**

In `score_findings()`, also populate parallel lists:
```python
confidences: list[float] = []
correct: list[bool] = []
```
For deterministic checks, confidence = 1.0. Correct = (status matches gold expectation).

Add these as mutable lists passed into `score_findings`.

- [ ] **Step 2: Run second pass for determinism**

In `main_async()`, after the first pass, run a second pass through the same manifests with a fresh store:
```python
# Second pass for determinism
run2_verdicts: dict[str, bool] = {}
for manifest in manifests:
    result = await run_document(manifest)
    if result and not result["error"]:
        for f in result["findings"]:
            run2_verdicts[f["check_id"]] = (f["status"] == "PASS")
```

- [ ] **Step 3: Compute ECE and determinism**

```python
from evaluation.metrics import compute_ece, determinism_score

ece = compute_ece(confidences, correct)
determinism = determinism_score(run1_verdicts, run2_verdicts)
```

- [ ] **Step 4: Add to gates table**

```python
report["gates"]["ece"] = {
    "value": round(ece, 4), "target": 0.05,
    "pass": ece <= 0.05,
}
report["gates"]["determinism"] = {
    "value": round(determinism, 4), "target": 1.0,
    "pass": determinism == 1.0,
}
report["gates"]["extraction_f1"] = {
    "value": round(extraction_f1, 4), "target": 0.95,
    "pass": (extraction_f1 or 0) >= 0.95,
}
```

- [ ] **Step 5: Print new gates**

In `print_report()`, the gates loop already prints all gates — no changes needed.

---

### Task 4: Run and verify

- [ ] **Step 1: Run limited test**

```bash
python evaluation/measure_v2.py --limit 10
```
Expected: reports extraction F1, ECE, determinism in gates; exits 0.

- [ ] **Step 2: Run full test suite**

```bash
pytest --ignore=test_nvidia.py --ignore=test_litert.py --ignore=tests/chaos
```
Expected: 328 passed.

- [ ] **Step 3: Update tracker.md and shortcomings.md**

- Mark M2.4 as in progress in tracker.md.
- In shortcomings.md §12, update the `compute_ece` has no callers entry.
