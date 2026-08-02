# M2.5 — Injection Golden Set Composition

**Date:** 2026-07-27
**Status:** Approved

## Goal

Add injection-laced PDFs to the golden set so the evaluation harness has a real security gate. Currently the `QUARANTINED_SECURITY` path is tested in unit tests but has zero coverage in the golden set — making the security gate vacuously true.

## Scope

- **10 injection PDFs** — one per technique from `tests/test_injection_corpus.py::INJECTION_CORPUS`. Each embeds the injection text as PDF body content, expects `QUARANTINED_SECURITY`.
- **4 benign PDFs** — one per entry from `BENIGN_CORPUS`. Each expects `READY` (no injection detected).
- **No layout diversity, no degraded variants.** Known gaps remain in shortcomings.md.

## Changes

### 1. `evaluation/golden_set/generator.py`

Add two new functions:

```python
def generate_injection_pdf(
    label: str, injection_text: str
) -> GeneratedDoc:
```

Uses `_make_pdf()` pattern (same as test_injection_corpus.py): creates a PyMuPDF doc, inserts injection text, returns `GeneratedDoc` with `doc_type="invoice_injection"`, defects=`["injection"]`, expected_findings=`[{"check_id": "INJECTION-SEC-001", "expected_status": "FAIL"}]`.

Additionally add a non-existent check ID `SEC-FLAG-001` that the harness will match to `QUARANTINED_SECURITY`.

```python
def generate_benign_pdf(
    label: str, benign_text: str
) -> GeneratedDoc:
```

Same but with no defects and expected_findings=[].

### 2. `build_corpus()` mode flag

Add `--include-injection` flag. When set, append injection + benign PDFs to the corpus after the synthetic docs.

### 3. Manifest pattern

- Injection docs: `INJ-<label>_gold.yaml`, document_id like `INJ-<label>`
- Benign docs: `BENIGN-<label>_gold.yaml`, document_id like `BENIGN-<label>`

### 4. Measure_v2.py

No changes needed — the harness already scores all manifests. The security path: injection docs will reach `QUARANTINED_SECURITY` status from the workflow, and `score_findings()` will count this as a finding against the `SEC-FLAG-001` gate.

Wait — need to verify: `QUARANTINED_SECURITY` workflows return early with no findings. The status doesn't set per-finding verdicts. This means we need a **new scoring path** — for documents that reach `QUARANTINED_SECURITY`, the harness should count that as a TP for the security gate instead of scoring per-check findings.

### 5. Gates addition

In `measure_v2.py`:
```python
"security_injection": {
    "value": injection_tp / (injection_tp + injection_fn) if total > 0 else 0,
    "target": 1.0,
    "pass": injection_recall == 1.0,
}
```

## Files touched

- `evaluation/golden_set/generator.py` — add injection PDF generation functions
- `evaluation/measure_v2.py` — add security injection scoring + gate
- No changes to injection detector or workflows

## Verification

```bash
python evaluation/golden_set/generator.py --include-injection
python evaluation/measure_v2.py --limit 15  # injection + benign docs
```
Expected: injection docs → QUARANTINED_SECURITY, benign docs → READY. Security gate PASS.
