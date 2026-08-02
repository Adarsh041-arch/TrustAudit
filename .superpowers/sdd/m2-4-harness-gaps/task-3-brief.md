# Task 3: Wire ECE and determinism

**Context:** `evaluation/metrics.py` has `compute_ece(confidences, correct, n_bins=10)` and `determinism_score(run1_verdicts, run2_verdicts)` — both are defined but never called. We need to wire them into `measure_v2.py`.

**Goal:** Run the golden set once for ECE calibration, run a second pass for determinism, add both to the gates table.

**Files:**
- Modify: `evaluation/measure_v2.py`

## Requirements

### 1. Collect confidence + correctness during scoring pass

The `score_findings()` function needs two new mutable lists passed in:
```python
confidences: list[float]  # confidence level of each finding (1.0 for deterministic checks)
correct: list[bool]       # whether the finding's verdict matches the golden expectation
```

Inside `score_findings()`, after each finding is classified as TP/FP/FN/TN, append:
- `confidences.append(1.0)` — all deterministic checks have confidence 1.0
- `correct.append(True)` if TP or TN; `correct.append(False)` if FP or FN

### 2. Run second pass for determinism

In `main_async()`, after the first loop and after computing extraction metrics, run a second pass:
```python
# Second pass for determinism
run1_verdicts: dict[str, bool] = {}
run2_verdicts: dict[str, bool] = {}
for i, manifest in enumerate(manifests):
    result1 = run1_results[i]  # reuse stored results from first pass if stored, or re-run
```

Actually, simplest approach: collect verdicts during the first pass into `run1_verdicts`, then run a second pass:

```python
# Second pass for determinism
from evaluation.metrics import determinism_score

# run1_verdicts was populated during score_findings calls in the main loop
run2_verdicts: dict[str, bool] = {}
for manifest in manifests:
    result = await run_document(manifest)
    if result and not result["error"]:
        for f in result["findings"]:
            if f["status"] in ("PASS", "FAIL"):
                run2_verdicts[f"{manifest['document_id']}:{f['check_id']}"] = (f["status"] == "PASS")

determinism = determinism_score(run1_verdicts, run2_verdicts)
```

Note: run1_verdicts should use the same key format `f"{doc_id}:{check_id}"`.

### 3. Compute ECE

After the main loop, compute:
```python
from evaluation.metrics import compute_ece
ece = compute_ece(confidences, correct)
```

### 4. Add to gates table

```python
"ece": {
    "value": round(ece, 4), "target": 0.05,
    "pass": ece <= 0.05,
},
"determinism": {
    "value": round(determinism, 4), "target": 1.0,
    "pass": determinism == 1.0,
},
```

### 5. Print in report

In `print_report()`, add:
```python
if "ece" in report.get("gates", {}):
    print(f"  ECE: {report['gates']['ece']['value']}")
if "determinism" in report.get("gates", {}):
    print(f"  Determinism: {report['gates']['determinism']['value']}")
```

The gates loop already prints all gates, but adding explicit labels is cleaner.

## Test

Run:
```
python evaluation/measure_v2.py --limit 3
```
Expected: exits non-zero (gates fail), ECE and determinism printed in gates.

Then full test suite:
```
pytest tests/ -x --ignore=test_nvidia.py --ignore=test_litert.py --ignore=tests/chaos
```
Expected: 328 passed.

## Report file

Write to: `.superpowers/sdd/m2-4-harness-gaps/task-3-report.md`
Contents: (1) commit SHA, (2) `measure_v2.py --limit 3` output, (3) full test suite result, (4) any concerns.
