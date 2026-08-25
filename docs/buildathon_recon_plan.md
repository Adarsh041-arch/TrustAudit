# AI Finance Controller — Buildathon Adaptation Plan

**Track 04:** AI Finance Controller — "Run the books and the cash position"  
**Base:** TrustAudit V2 (`audit_v2/` codebase, port `:8100`)  
**Goal:** Close a finance-ops reconciliation loop across a 100-record synthetic batch, reporting match rate and honest exceptions.

---

## Overview

Adapt TrustAudit's deterministic validation engine from compliance-checking invoices/POs/receipts into a three-way payment reconciliation engine that matches:

| Source | Represents | Format |
|--------|-----------|--------|
| `payout_report.csv` | What Razorpay says it paid | txn_id, amount, date, status |
| `bank_statement.csv` | What the bank actually credited | ref, credited_amount, value_date |
| `ledger.csv` | What was internally expected | invoice_id, expected_amount, due_date, counterparty |

**Output:** Match rate (e.g. 94/100), exception table with machine-classified reason + LLM-generated plain-language explanation, DOCX/PDF report.

---

## Architecture — What is Reused vs New

### Reused Directly (No Change)

| Component | File | Used For |
|-----------|------|----------|
| `Decimal` arithmetic engine | `audit_v2/domain/validators/arithmetic.py` | Exact amount comparison |
| `ToleranceSpec` model | `audit_v2/domain/models.py:122` | ±₹100 fee tolerance bands |
| `CorpusIndex` + `build_corpus_index` | `audit_v2/domain/correlation.py` | Cross-source key indexing pattern |
| Duplicate detection logic | `audit_v2/domain/validators/duplicate.py` | Duplicate transaction ID check |
| `CheckResult` pattern | `audit_v2/domain/models.py` | MATCHED / EXCEPTION / SKIPPED verdicts |
| Cryptographic fingerprinting | `audit_v2/domain/models.py:Finding` | Reproducible decision audit trail |
| DOCX/PDF report builders | `audit_v2/reporting/report_builders.py` | Adapted for exception report |
| FastAPI server skeleton | `audit_v2/server.py` | New `/api/recon/*` endpoints added |
| React dashboard | `audit-frontend/src/AppV2.tsx` | Reskinned for match rate + exception table |
| NvidiaGateway | `audit_v2/gateway/nvidia_gateway.py` | LLM call for exception explanation |
| Prompt-injection defenses | `audit_v2/security/` | Keep — LLM still reads text |

### New Code

| Component | New file | Purpose |
|-----------|----------|---------|
| Domain models | `reconcile/models.py` | `PayoutRecord`, `BankEntry`, `LedgerRecord`, `MatchResult`, `ReconciliationRun` |
| CSV ingestion | `reconcile/ingest.py` | Parse 3 CSVs into typed Decimal-field records |
| Matcher | `reconcile/matcher.py` | Deterministic 3-way join logic |
| Exception classifier | `reconcile/classifier.py` | Assigns exception type (deterministic, rule-based) |
| LLM explainer | `reconcile/explainer.py` | Calls NvidiaGateway to produce plain-language reason |
| Report builder | `reconcile/reporter.py` | Match rate + exception table in DOCX/PDF |
| API router | `reconcile/api.py` | Mounted into `audit_v2/server.py` at `/api/recon/` |
| Synthetic data generator | `generate_recon_batch.py` | Produces 100 records across 3 CSVs with injected breaks |
| Ground truth | `evaluation/recon_ground_truth.json` | Known breaks for honest metric verification |
| Evaluation harness | `evaluation/evaluate_recon.py` | Compares engine output to ground truth |
| Dashboard component | `audit-frontend/src/sections/ReconciliationSection.tsx` | Match rate banner, exception drilldown |

---

## Phase 1 — Synthetic Data Generator (Day 1)

**New file:** `generate_recon_batch.py`

### What it generates

100 synthetic transactions:
- `payout_report.csv`: 100 rows — txn_id, payout_amount (INR, 4 decimal places), payout_date, settlement_status
- `bank_statement.csv`: 97 rows — bank_ref, credited_amount, value_date, counterparty
- `ledger.csv`: 100 rows — invoice_id, expected_amount, due_date, payer_id, currency

### Deliberate injected mismatches (the "ground truth")

| Break type | Count | Details |
|-----------|-------|---------|
| **Amount mismatch** | 5 | Razorpay payout is ₹25–₹100 short (processing fee deduction) |
| **Missing bank credit** | 3 | Payout exists in report but no bank entry (settlement failure) |
| **Missing ledger entry** | 2 | Bank credited money with no ledger counterpart |
| **Duplicate txn_id** | 2 | Same transaction_id appears twice in payout_report |
| **Date drift** | 3 | Bank credits 1–3 days after payout date |
| **Currency mismatch** | 1 | Ledger has USD, bank credit has INR equivalent |
| Clean matches | 84 | All three sources agree exactly |

All injected breaks recorded in `evaluation/recon_ground_truth.json`:
```json
{
  "total_records": 100,
  "clean_matches": 84,
  "breaks": [
    {"txn_id": "TXN1042", "type": "AMOUNT_MISMATCH", "delta": "-50.00", "reason": "processing_fee"},
    {"txn_id": "TXN1055", "type": "MISSING_BANK_CREDIT"},
    ...
  ]
}
```

### CLI interface
```bash
python generate_recon_batch.py --records 100 --seed 42 --out data/recon/
```
`--seed` ensures reproducible output — judges can re-run and get the same files.

---

## Phase 2 — Domain Models (Day 2, morning)

**New file:** `reconcile/models.py`

### Core data classes (all Decimal, no float)

```python
class PayoutRecord(BaseModel):
    txn_id: str
    payout_amount: Decimal          # always Decimal, never float
    payout_date: date
    settlement_status: str
    currency: str = "INR"

class BankEntry(BaseModel):
    bank_ref: str
    credited_amount: Decimal
    value_date: date
    counterparty: str | None
    currency: str = "INR"

class LedgerRecord(BaseModel):
    invoice_id: str
    expected_amount: Decimal
    due_date: date
    payer_id: str
    currency: str = "INR"

class MatchStatus(StrEnum):
    MATCHED   = "MATCHED"           # all 3 sources agree within tolerance
    EXCEPTION = "EXCEPTION"         # deterministic mismatch found
    PARTIAL   = "PARTIAL"           # 2 of 3 sources matched
    UNMATCHED = "UNMATCHED"         # no counterpart found in 1+ sources

class ExceptionType(StrEnum):
    AMOUNT_MISMATCH     = "AMOUNT_MISMATCH"
    MISSING_BANK_CREDIT = "MISSING_BANK_CREDIT"
    MISSING_LEDGER      = "MISSING_LEDGER"
    DUPLICATE_TXN_ID    = "DUPLICATE_TXN_ID"
    DATE_DRIFT          = "DATE_DRIFT"
    CURRENCY_MISMATCH   = "CURRENCY_MISMATCH"

class MatchResult(BaseModel):
    txn_id: str
    status: MatchStatus
    payout: PayoutRecord | None
    bank: BankEntry | None
    ledger: LedgerRecord | None
    exception_type: ExceptionType | None = None
    amount_delta: Decimal | None = None         # Decimal diff, if relevant
    date_drift_days: int | None = None
    decision_fingerprint: str                   # sha256 for reproducibility
    llm_explanation: str | None = None          # populated after LLM pass

class ReconciliationRun(BaseModel):
    run_id: str
    run_at: datetime
    total: int
    matched: int
    exceptions: int
    match_rate: Decimal                         # e.g. Decimal("0.94")
    results: list[MatchResult]
    llm_summary: str | None = None
```

---

## Phase 3 — Matching Engine (Day 2, afternoon)

**New file:** `reconcile/matcher.py`

### Matching logic (fully deterministic — no LLM)

```
Step 1: Load all 3 CSVs via reconcile/ingest.py
Step 2: Build lookup indices
  - payout_by_txn_id: dict[str, PayoutRecord]
  - bank_by_ref: dict[str, BankEntry]
  - ledger_by_invoice_id: dict[str, LedgerRecord]
  - payout_by_signature: dict[str, list[PayoutRecord]]  → duplicate detection

Step 3: For each PayoutRecord:
  a) match_exact(payout, bank):
       same reference ID AND |payout_amount - credited_amount| == Decimal("0")
       → MatchStatus.MATCHED

  b) match_with_tolerance(payout, bank, tolerance=Decimal("100")):
       same reference ID AND |payout_amount - credited_amount| ≤ ₹100
       → MatchStatus.MATCHED (amount_delta recorded)

  c) match_date_drift(payout, bank, max_days=3):
       same reference ID AND amounts match AND |date_diff| ≤ 3 days
       → MatchStatus.MATCHED (date_drift_days recorded)

  d) match_ledger(payout, ledger):
       payout.txn_id resolves to ledger.invoice_id AND amounts agree in tolerance

  e) no match → MatchStatus.EXCEPTION or UNMATCHED

Step 4: classify_exception() assigns ExceptionType (deterministic rule)
Step 5: compute_fingerprint() hashes (txn_id + amounts + dates + rule_version)
Step 6: Aggregate matched_count, exception_count, match_rate
```

### Tolerance spec (reuses existing ToleranceSpec from audit_v2/domain/models.py)

```python
FEE_TOLERANCE    = ToleranceSpec(type="absolute", value="100")  # ±₹100 gateway fees
DATE_TOLERANCE_DAYS = 3                                           # ≤3 days settlement lag
```

---

## Phase 4 — Exception Classifier (Day 2, late afternoon)

**New file:** `reconcile/classifier.py`

Pure rule-based logic — no model calls. Assigns `ExceptionType` based on
what is and is not present in the match attempt:

```python
def classify(payout, bank, ledger, amount_delta, date_drift_days) -> ExceptionType:
    if payout is None:
        return ExceptionType.MISSING_LEDGER   # bank credit exists, no payout
    if bank is None:
        return ExceptionType.MISSING_BANK_CREDIT
    if payout.currency != bank.currency:
        return ExceptionType.CURRENCY_MISMATCH
    if date_drift_days and date_drift_days > DATE_TOLERANCE_DAYS:
        return ExceptionType.DATE_DRIFT
    if amount_delta and abs(amount_delta) > FEE_TOLERANCE.as_decimal():
        return ExceptionType.AMOUNT_MISMATCH
    ...
```

---

## Phase 5 — LLM Explainer (Day 3, morning)

**New file:** `reconcile/explainer.py`

### What LLM does and does NOT do

```
LLM does NOT: decide whether something is matched or not (code does this)
LLM does NOT: produce the match rate number (counted from MatchStatus values)
LLM does NOT: assign ExceptionType (deterministic classifier does this)
LLM does NOT: see raw CSV data (only structured exception dict)

LLM DOES: turn a structured exception dict into plain English (1–2 sentences)
LLM DOES: produce a 3-sentence overall run summary for the pitch
```

### Implementation sketch

```python
def explain_exception(result: MatchResult, gateway: NvidiaGateway) -> str:
    """
    Input:  MatchResult with exception_type, amounts, delta already computed.
    Output: 1–2 sentence human-readable reason. Cannot change verdict or delta.
    """
    prompt = build_structured_prompt(result)   # no raw user text in prompt
    response = gateway.extract(images=[], prompt=prompt, tenant_id="recon")
    return response.content.strip()

def summarize_run(run: ReconciliationRun, gateway: NvidiaGateway) -> str:
    """3-sentence pitch-ready summary over already-computed run metrics."""
    ...
```

---

## Phase 6 — Report Builder (Day 3, afternoon)

**New file:** `reconcile/reporter.py` (adapts `audit_v2/reporting/report_builders.py`)

### Report structure

```
Header:
  Run ID · Timestamp · Total records processed

Match Rate (large, prominent):
  94 / 100  MATCHED  →  94.0%

Executive Summary (LLM-generated, 3 sentences):
  "94 of 100 payout records matched across all three sources..."

Exception Table:
  | Txn ID | Type | Payout Amt | Bank Amt | Delta | Drift | AI Explanation |

Per-exception drilldown: all 3 source rows side-by-side

Footer:
  Decision fingerprint per verdict · Ruleset version · Tolerance band applied
```

---

## Phase 7 — API Endpoints (Day 3, afternoon)

**New file:** `reconcile/api.py` — mounted into `audit_v2/server.py` at `/api/recon/`

```
POST /api/recon/run
  body: multipart — payout_report.csv, bank_statement.csv, ledger.csv
  returns: ReconciliationRun JSON

GET  /api/recon/results/{run_id}
  returns: cached ReconciliationRun with llm_explanation populated

POST /api/recon/report?format=docx|pdf
  body: ReconciliationRun JSON
  returns: binary report file

GET  /api/recon/health
  returns: { match_rate, last_run_id, total_runs_this_session }
```

---

## Phase 8 — Dashboard (Day 4)

**New file:** `audit-frontend/src/sections/ReconciliationSection.tsx`  
**Modify:** `audit-frontend/src/AppV2.tsx` — add Reconciliation tab

### UI components

```
Match Rate Banner (top center):
  94 / 100 MATCHED  →  94.0%
  (large, prominent — this is what judges see first)

Source File Upload:
  3 drag-and-drop zones (payout CSV · bank CSV · ledger CSV)
  + Run Reconciliation button

Exception Table (main body):
  Sortable + filterable by ExceptionType
  Click row → side-by-side source record drilldown

LLM Explanation column:
  Plain text, clearly labeled "AI-generated explanation"

Run Summary:
  LLM paragraph, labeled "AI-generated summary — verified by deterministic engine"
```

---

## Phase 9 — Testing & Verification (Day 4–5)

### Test files to write

```
tests/recon/
  test_matcher_exact_match.py        — 3 sources agree → MATCHED
  test_matcher_fee_tolerance.py      — ₹50 short → MATCHED with note
  test_matcher_missing_bank.py       — no bank entry → MISSING_BANK_CREDIT
  test_matcher_duplicate.py          — duplicate txn_id → DUPLICATE_TXN_ID
  test_matcher_date_drift.py         — 2 days → MATCHED; 5 days → DATE_DRIFT
  test_classifier.py                 — exception type assignment (all deterministic)
  test_ground_truth.py               — run on synthetic batch, compare to ground_truth.json
```

### Ground truth validation (pitch defense)

```bash
python evaluation/evaluate_recon.py \
  --batch data/recon/ \
  --truth evaluation/recon_ground_truth.json

# Expected output:
# Engine MATCHED:   87/100 (84 clean + 3 fee-tolerance)
# Ground truth:     87 expected → PASS (100% agreement)
# False positives:  0
# False negatives:  0
```

---

## File Structure After Build

```
reconcile/                              ← NEW MODULE
  __init__.py
  models.py                            ← PayoutRecord, BankEntry, LedgerRecord, MatchResult
  ingest.py                            ← CSV → typed models with Decimal parsing
  matcher.py                           ← deterministic 3-way join
  classifier.py                        ← ExceptionType assignment (rule-based)
  explainer.py                         ← LLM calls only (explain + summarize)
  reporter.py                          ← DOCX/PDF adapted from report_builders.py
  api.py                               ← FastAPI router, mounted in audit_v2/server.py

generate_recon_batch.py                ← NEW — synthetic data generator (CLI)
evaluation/
  recon_ground_truth.json              ← NEW — injected breaks manifest
  evaluate_recon.py                    ← NEW — ground truth validation harness

data/recon/                            ← Generated locally (gitignored)
  payout_report.csv
  bank_statement.csv
  ledger.csv

audit-frontend/src/sections/
  ReconciliationSection.tsx            ← NEW — match rate banner, exception table

tests/recon/                           ← NEW — reconciliation unit tests
```

---

## Reuse Map (What Not to Touch)

| Existing file | Status | Notes |
|--------------|--------|-------|
| `audit_v2/domain/validators/arithmetic.py` | Keep | Import Decimal logic only |
| `audit_v2/domain/validators/duplicate.py` | Keep | Import `_others()` pattern |
| `audit_v2/domain/validators/threshold.py` | Keep | Import `ToleranceSpec.apply()` |
| `audit_v2/domain/models.py` | Keep | Import `ToleranceSpec`, `CheckResult` pattern |
| `audit_v2/domain/correlation.py` | Keep | Pattern reference for index building |
| `audit_v2/gateway/nvidia_gateway.py` | Keep | Call `.extract()` for LLM explain/summarize |
| `audit_v2/reporting/report_builders.py` | Keep | Adapt into `reconcile/reporter.py` |
| `audit_v2/server.py` | Extend | Mount `reconcile/api.py` at `/api/recon/` |
| `audit-frontend/src/AppV2.tsx` | Extend | Add Reconciliation tab |
| V1 (`app/`, `backend/`, V1 frontend) | Frozen | AGENTS.md cardinal rule |

---

## LLM Boundary — Summary

```
DETERMINISTIC CODE (Python + Decimal)
  ✔ CSV ingestion and field parsing
  ✔ Amount comparison (exact and tolerance band)
  ✔ Date drift calculation
  ✔ Duplicate transaction ID detection
  ✔ Exception type classification
  ✔ MATCHED / EXCEPTION / UNMATCHED verdict assignment
  ✔ Match rate arithmetic (matched / total * 100)
  ✔ Decision fingerprint generation

LLM (NvidiaGateway — structured prompt only)
  ✔ explain_exception(): 1-sentence plain-language reason per exception
  ✔ summarize_run(): 3-sentence pitch-ready overview
  ✗ Never changes a verdict or touches a number
```

---

## Build Order by Day

| Day | Focus | Deliverable |
|-----|-------|-------------|
| Day 1 | `generate_recon_batch.py` | 3 CSVs + `recon_ground_truth.json` |
| Day 2 AM | `reconcile/models.py` + `reconcile/ingest.py` | Typed models, CSV parsing |
| Day 2 PM | `reconcile/matcher.py` + `reconcile/classifier.py` | Working matcher, unit tests pass |
| Day 3 AM | `reconcile/explainer.py` | LLM explain + summarize calls working |
| Day 3 PM | `reconcile/reporter.py` + `reconcile/api.py` | Report generation + API endpoints |
| Day 4 | `ReconciliationSection.tsx` + dashboard integration | UI with match rate banner |
| Day 5 | `evaluate_recon.py` + ground truth validation + demo | Verified metrics, pitch recording |

---

## Pitch Story (the "failure-recovery" moment)

> "My matcher initially flagged all ₹50 fee deductions as exceptions — 5 legitimate transactions getting false-positive exceptions. I diagnosed it from the ground truth manifest, which showed all were exactly ₹25–₹100 short. I added a configurable `FEE_TOLERANCE` band (₹0–₹100 absolute, Decimal arithmetic, not a LLM guess), re-ran, and those 5 moved from EXCEPTION to MATCHED. Match rate went from 89% to 94%. The LLM then explains those toleranced matches as 'likely processing fee deduction' — but the code made the call."

---

> **Cardinal rule preserved:** `reconcile/` must not import from `app/` or `backend/`.
> Enforced by existing `.importlinter` config — add `reconcile` to allowed modules list.
