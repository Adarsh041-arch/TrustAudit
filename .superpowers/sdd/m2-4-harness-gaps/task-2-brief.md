# Task 2: Implement score_extraction() in measure_v2.py

**Context:** The golden manifests carry `expected_fields` (header values) and `expected_lines` (line-item arrays). `evaluation/measure_v2.py` has a `score_extraction()` stub that does nothing. Task 1 already made `ExtractedDocument` available in `AuditWorkflowOutput.document`.

**Goal:** Implement `score_extraction()` to compare extracted fields against golden manifest and wire it into the main scoring loop.

**Files:**
- Modify: `evaluation/measure_v2.py`

## Requirements

### 1. `_decimal_equal(a: str, b: str, tolerance: str | None = None) -> bool`

Add a helper function. Compare two decimal strings, handling commas, and optional tolerance:

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
        return a.strip().casefold() == b.strip().casefold()
```

### 2. Replace the `score_extraction()` stub

Current stub (lines 157-162) does nothing. Replace it with real logic:

```python
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
```

### 3. Pipe `document` through `run_document()`

In `run_document()` (line 75), add to the return dict:
```python
"document": out.document.model_dump() if out.document else None,
```

Import `BaseModel` if needed for type checking — `model_dump()` is a Pydantic BaseModel method, and `ExtractedDocument` inherits from `BaseModel`.

### 4. Wire into `main_async()`

In `main_async()` (around line 189), after `score_findings(...)`, add:
```python
score_extraction(manifest, result, field_stats)
```

Initialize `field_stats = {}` at the top of the function alongside the other collectors.

After the loop, compute extraction F1:
```python
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
```

### 5. Print extraction metrics

In `print_report()`, add after the gates:
```python
if report.get("extraction"):
    print(f"\nExtraction field F1: {report['extraction']['f1']:.4f}"
          f"  (TP={report['extraction']['tp']}, "
          f"FP={report['extraction']['fp']}, "
          f"FN={report['extraction']['fn']})")
```

### 6. Add extraction gate

In `main_async()`, add to the `report["gates"]` dict:
```python
"extraction_f1": {
    "value": round(report["extraction"]["f1"], 4) if report.get("extraction") else 0.0,
    "target": 0.95,
    "pass": (report.get("extraction", {}).get("f1") or 0) >= 0.95,
},
```

## Test

Run:
```
python evaluation/measure_v2.py --limit 5
```
Expected: exits 0, extraction F1 printed.

Then full test suite:
```
pytest tests/ -x --ignore=test_nvidia.py --ignore=test_litert.py --ignore=tests/chaos
```
Expected: 328 passed.

## Report file

Write report to: `.superpowers/sdd/m2-4-harness-gaps/task-2-report.md`
Contents: (1) commit SHA, (2) `measure_v2.py --limit 5` output, (3) full test suite result, (4) any concerns.
