# M2.4 — §6 Harness Gaps

**Date:** 2026-07-27
**Status:** Approved

## What

Close two gaps in the evaluation harness (`evaluation/measure_v2.py`):

1. **`score_extraction()` is a no-op** — golden manifests carry `expected_fields` (header values like vendor_gstin, grand_total, subtotal) and `expected_lines` (line-item arrays). The function should compare extracted output vs gold and report field-level F1.

2. **`compute_ece()` and `determinism_score()` exist in `evaluation/metrics.py` but are never called** — need to wire them into `measure_v2.py` for calibration and repeat-run agreement.

## Changes

### 1. Pipe `ExtractedDocument` through `AuditWorkflowOutput`

Extraction scoring needs the real `ExtractedDocument` back from the workflow. Add an optional `document` field to `audit_v2/orchestration/workflows.py::AuditWorkflowOutput` and populate it on the success path.

### 2. `score_extraction()` — header fields + line items

- For each `expected_fields` key: check if the extracted `DocumentHeader` has it and whether the `.decimal_value` or `.text` matches the gold value.
- For `expected_lines`: compare by tuple `(qty, rate, total, hsn)`. Use fuzzy matching (decimal_equal with tolerance) for numeric fields.
- Compute per-field precision/recall/F1, aggregate to overall extraction F1.

### 3. Wire ECE and determinism

- After the main scoring pass, run a **second pass** through the same documents. Compare each finding's PASS/FAIL verdict against the golden manifest to determine "correct" vs "incorrect".
- Confidence = model confidence (1.0 for deterministic checks since they're exact).
- Feed (confidences, correct_bool) into `compute_ece()`.
- Feed (run1_verdicts, run2_verdicts) into `determinism_score()`.
- Add ECE and determinism to the gates table.

### 4. Gates table additions

| Gate | Target | Method |
|------|--------|--------|
| Extraction field F1 | ≥0.95 | `score_extraction()` |
| ECE | ≤0.05 | `compute_ece(confidences, corrects)` |
| Determinism | 1.00 | `determinism_score(run1, run2)` |

## Files touched

- `audit_v2/orchestration/workflows.py` — add `document: ExtractedDocument | None` to output
- `evaluation/measure_v2.py` — implement `score_extraction()`, wire ECE + determinism
- `evaluation/metrics.py` — no changes needed (functions already exist)

## Verification

Run `python evaluation/measure_v2.py --limit 10` — should produce extraction F1, ECE, determinism in the report.
