# Implementation Tracker

**Project:** Multi-Model Document Audit Agent (V2)
**Plan source:** `PHASES_V2.md`
**Started:** 2026-07-25
**Current build:** 2026-07-27
**Active milestones:** M0 Foundations ✅ · M1 Thin Slice ✅ · M2 Hardening ✅
**Approach:** Vertical Slice (per `AGENTS.md` §10, M1 is deliberately narrow and first)

---

## Build Log

### 2026-08-02 (session 5d) — Audit V2 Frontend UI & FastAPI Server (:8100) Shipped

Completed Frontend Execution for Audit V2:

- **`backend/server_v2.py`** — Production FastAPI backend on port `:8100` exposing multi-file batch document upload (`files: list[UploadFile]`), 3-way match cluster correlation, active findings, hash-chained audit log with live `verify_chain()` validation, and human review queue endpoints.
- **`audit-frontend/`** — Built modern React dashboard aligned with V1 design system:
  - **Live Audit Ingestion**: Multi-file batch document selection (`multiple` input) with document count badge, VLM Vision AI status badges, and header extraction stats.
  - **3-Way Match Topology**: Interactive visual cluster viewer (PO ↔ DC ↔ Invoice) and critical over-billing fraud alerts.
  - **Findings Inspector**: Active findings with decision fingerprints.
  - **Human Review Queue**: Priority workspace (`severity × value × age`) with `Confirm`, `Reject (False Alarm)`, and `Escalate` actions.
  - **Cryptographic Audit Log**: Visual hash-chain timeline with real-time SHA-256 integrity verification badge.
- **Tests**: Created `tests/test_server_v2.py` (all 6 API tests passing including `test_upload_multi_document_batch`), `npm run build` clean in 850ms.



Completed Phases 8, 9, and 10 (PHASES_V2 §4):

- **`audit_v2/domain/adjudicator.py`** — Phase 8 model-assisted adjudicator. Structural invariant enforced: adjudicator can NEVER overturn deterministic math verdicts. Resolves two-vendor extraction disagreements and routes to human review.
- **`audit_v2/persistence/provenance.py`** — Phase 9 immutable evidence DAG tracking `finding -> check -> rule_version -> document -> page -> bbox -> extracted_field`.
- **`audit_v2/orchestration/review_queue.py`** — Phase 10 human review priority queue (`severity x value x age`), reviewer action history (`CONFIRM`, `REJECT_FALSE_POSITIVE`, `ESCALATE`), and golden-set candidate feedback loop.
- **`audit_v2/persistence/{audit_log.py, permission_matrix.py}`** — Phase 2 governance controls: hash-chained audit log with `verify_chain()` + RBAC and Separation of Duties enforcement.
- **Tests**: Added `test_adjudicator.py`, `test_provenance.py`, `test_review_queue.py`, `test_audit_log.py`, `test_permission_matrix.py` (all 353 tests passing).


Completed Phase 4 completion & Phase 5.1 (PHASES_V2 §4):

- **`audit_v2/gateway/nvidia_gateway.py`** — Multimodal VLM gateway connecting to NVIDIA OpenAI-compatible API (`https://integrate.api.nvidia.com/v1`). Integrated Phase 2 governance PII redactor before model calls + retry with backoff.
- **`audit_v2/extraction/vlm_extractor.py`** — PyMuPDF 200 DPI JPEG rendering + structured JSON extraction prompt requesting header, line item, and tax line values.
- **`audit_v2/orchestration/activities.py`** — Added `_try_vlm_fallback` in `extract_document` for scanned PDFs and image files without text layers.
- **Tests**: Added `tests/test_nvidia_gateway.py` and `tests/test_vlm_extractor.py` (API key validation, PII redaction, gateway retry, JSON block cleaning, ExtractedDocument mapping).
- **Quality**: `ruff check --fix` clean, all unit tests passing.


Completed Phase 7 (PHASES_V2 §4 Phase 7):

- **`audit_v2/domain/correlation.py`** — 3-tier document clustering (`build_clusters`): explicit PO reference (0.98 confidence), `(vendor, amount, date-window)` (0.80), and fuzzy vendor+line-description overlap (0.60). Per-tenant `build_corpus_index` for duplicate detection.
- **Corpus & 3-Way Match Validators**:
  - `audit_v2/domain/validators/threeway.py` — `CHK-XDOC-QTY-001` (invoiced <= received), `CHK-XDOC-PRICE-001` (price vs PO), `CHK-XDOC-RECEIPT-001` (goods receipt requirement), `CHK-XDOC-CUMUL-001` (split-invoice over-billing across cluster).
  - `audit_v2/domain/validators/duplicate.py` — `CHK-DUP-DOC-001` (exact vendor+docnum & near duplicate).
  - `audit_v2/domain/validators/reference_integrity.py` — `CHK-REF-QTY-001/002` (quantity vs PO & DC).
- **`audit_v2/orchestration/cluster_audit.py`** — `ClusterAuditor` supporting accumulation of document arrivals, cluster re-evaluation, and `supersedes` lifecycle tracking for findings (e.g. invoice arriving before PO).
- **`tests/test_correlation.py`** — 35+ test cases covering link methods, three-way match, over-billing, duplicate detection, and late-arrival supersedes lifecycle.
- **Gates:** pytest suite 308 → **349 passed** (8 skipped infra/chaos tests). Clean build.


### 2026-07-26 (session 3b) — Temporal durable execution validated and integrated

`AuditDocumentWorkflow` (`@workflow.defn`), 7 `@activity.defn` activities,
worker entrypoint, and 5 integration tests via Temporal's time-skipping
`WorkflowEnvironment`. The golden invoice reproduces the plain workflow's
exact 3 FAILs through the Temporal path. Validation of the drafted files
found and fixed before commit:

- **`RetryPolicy(maximum_attempts=0)` means *unlimited* in Temporal** — a
  crashing security scan would have retried forever. Now 1.
- **`ValidateAndEmitResult.findings = list`** — default was the `list` type,
  not an instance; every error path would have crashed. Now
  `field(default_factory=list)` + regression test.
- **Duplicated check logic** — the Temporal emit activity re-implemented the
  routing/validation/finding block from `AuditWorkflow.run`. Extracted into
  shared `run_checks_and_emit()` (`workflows.py`); both paths call it, so
  they cannot drift. Full suite + 200-doc golden run re-verified after the
  refactor.
- `duplicate_of` carried the error string instead of the duplicate's
  document_id; quarantine/FAILED statuses were not persisted on early exits;
  POISON retry was 1 attempt where §3.3 says "1 retry then quarantine" (=2);
  raw `update_status` bypassed the `transition_document` state-machine guard;
  no-data path returned RECEIVED where the plain workflow returns READY.

**Known ceilings (unchanged):** `MemoryDocumentStore` is per-worker-process —
meaningless durability with a real Temporal server until Postgres lands; PDF
bytes travel through workflow history (needs blob storage); the
`docker-compose` server and the §7.4 worker-kill chaos test are still
unexercised. Restart safety now has a *mechanism*, not yet a *proof*.

### 2026-07-26 (session 3) — Golden set 1 → 200 and measured §6 gates

The recall/F1 gates were previously unmeasurable (golden set of 1). Built:

- **`evaluation/golden_set/generator.py`** — deterministic synthetic corpus
  generator (seeded RNG, pinned PDF `/CreationDate`, fixed base date). 200 docs
  / 30 vendor clusters: 140 invoices, 30 POs, 15 DCs, 15 GRNs; 74 documents
  carry 1–2 seeded defects from a 9-defect taxonomy, each mapped to the exact
  check IDs it must trip. Gold manifests carry expected findings + field values.
- **`evaluation/measure_v2.py`** — §6 harness: runs `AuditWorkflow` over every
  golden doc, scores TP/FP/FN/TN per check category, prints the gate table,
  writes `evaluation/baselines/v2.json`, exits non-zero on any gate failure.
- **`tests/test_golden_set_eval.py`** — generator determinism (byte-identical
  PDFs for same seed) + 12-doc end-to-end defect-detection smoke test in CI.

**Bugs the corpus caught immediately** (the whole point of the exercise):

1. **Phantom PO reference** — `po_reference` regex matched "PO" inside
   "Network Switch 24-**po**rt", capturing "rt", so `missing_po_ref` invoices
   still passed CHK-REF-PO-001 (7 misses). Fixed with word boundaries and a
   mandatory colon.
2. **DC/GRN dates landed in the wrong field** — both extractors stored the
   document date as `invoice_date`, so `delivery_date`/`grn_date` were always
   None and CHK-FORMAT-MANDATORY-001 false-alarmed on every clean DC/GRN.
   Fixed; extractor tests updated.
3. Generator crash on 2-defect sampling from a 1-defect PO pool (min-clamped).

**Measured result (200 docs, seed 42):** arithmetic P/R = **1.00/1.00**
(90 TP, 0 FP, 0 FN), reference_integrity 1.00/1.00, threshold 1.00/1.00,
format_completeness 1.00/1.00, overall **P 1.00 / R 1.00 / F1 1.00**.
All four §6 finding gates PASS. Honest caveats: the corpus is synthetic and
rendered by the same layout family the extractors were tuned on — it measures
the deterministic engine, not extraction robustness on real-world scans;
temporal/sequence/rollforward rows are 0 because no defects are seeded for
them yet (corpus-level and cross-doc checks are Phase 7).

### 2026-07-26 (session 2) — Correctness audit and remediation of Phases 0–6

An audit of the implementation against `PHASES_V2.md` §§0–6 found that several
rows previously marked ✅ were not doing what they claimed. Details and file
references in `shortcomings.md` §11. Summary:

- **Routing was computed and thrown away.** `AuditWorkflow` called `resolve()`
  then ran a hardcoded one-element check list, so **1 of 29 checks executed**.
  `contracts/routing_rules.yaml` also named 5 check IDs absent from the catalog.
  Both fixed; the golden invoice now runs **25 checks** (was 1).
- **Extraction fused table columns** — spans joined with `""` turned
  `8471 | 2 | 45,000.00` into `8471245,000.00`, producing false arithmetic
  failures. Also fixed: grand_total matching the wrong row, subtotal and bank
  details never extracted, and tax lines never matching (0 extracted).
- **Fabricated GST rate table removed** — `_prescribed_rate_for_hsn` guessed
  rates from HSN prefixes and paired tax lines by positional index.
- **Checks that reported compliant without checking** — `duplicate` returned
  unconditional PASS; validator exceptions became FAIL findings (§3.3 violation);
  `check_discount_cap` was unfailable; `check_hsn_code` rejected legal 4-digit HSNs.
- **§5 security implemented from zero** — injection + invisible-text detection,
  wired to `QUARANTINED_SECURITY`, with a 10-technique red-team corpus.
- **§3.5 coverage integrity enforced** — incomplete coverage now yields
  `INCOMPLETE`, never `READY`.
- **Fingerprint made content-addressed** — previously included `document_id`,
  defeating the §8 cache, and omitted grand_total/dates/GSTIN.

**Gates:** tests 186 → **308**; validator branch coverage 64% → **99%**
(`--cov-fail-under=95` now enforced); import-linter replaced grep with real
contracts including a **domain-purity rule** (structural guard against B1);
mypy extended from `domain/` to the whole tree, clean across 46 files;
property-based, determinism, and catalog/registry/routing-consistency suites added.

### 2026-07-26 — M0 (Foundations) + M1 (Thin Slice) shipped
- **M0.5 V1 baseline** now runs for real: `evaluation/measure_v1_baseline.py` invokes `app.graph.build_graph()` and scores against `evaluation/golden_set/manifests/*.yaml`. Macros P/R/F1 = **1.00 / 0.17 / 0.29** on the only manifest we have (`doc_gold_inv_001`). This is the empirical floor V2 must beat. Adds `evaluation/offline_shims.py` (Gemini API stub) and `evaluation/stub_vlm.py` (reproduction of V1's LLM-Does-Math failure mode for offline comparison).
- **M1 emission layer:** `audit_v2/domain/finding_generator.py` turns `CheckResult` → `Finding` with `decision_fingerprint = sha256(ruleset|prompt|model|extractor|document_hash)`. `audit_v2/domain/catalog_loader.py` parses the machine-readable check catalog. Both wired into `audit_v2/orchestration/workflows.py::AuditWorkflow.run`.
- **M1 tests:** 9 new tests (186 total, all green):
  - `tests/test_finding_generator.py` (4) — PASS emission, FAIL with evidence/delta, fingerprint stability, fingerprint changes with ruleset bump.
  - `tests/test_thin_slice.py` (2) — golden invoice detects the 3 stated-arithmetic FAILs, consistent invoice emits zero fails.
  - `tests/test_workflow_thin_slice.py` (3) — golden PDF end-to-end through `AuditWorkflow`, missing-doc → FAILED, encrypted-PDF → QUARANTINED_ENCRYPTED.
- **Documents updated:** `tracker.md` (this file), `shortcomings.md` (new §8 + §9).

### Outstanding for next milestone (M2)
- Temporal dev stack from `docker-compose.yml` is not yet exercised — `AuditWorkflow` is still a plain Python class.
- Chaos test for "worker killed mid-batch" — relies on Temporal's replay guarantees; needs the dev stack to be honest about it.
- Reconciliation job runs only against in-memory store; needs Postgres RLS to be a real signal.

---

## Phase 0 — Foundations

| Step | File(s) | Action | Status |
|------|---------|--------|--------|
| P0.1 | `audit_v2/`, `contracts/`, `evaluation/`, `.github/`, `tests/` | Create directory skeleton | ✅ |
| P0.2 | `audit_v2/pyproject.toml` | Project config, deps, tool settings | ✅ |
| P0.3 | `contracts/schemas/{document,coverage,provenance,finding,check_catalog_entry,check_catalog}.json` | JSON Schema contracts (6 files) | ✅ |
| P0.4 | `docker-compose.yml` | Local dev stack (Postgres 16, MinIO, Temporal) | ✅ |
| P0.5 | `evaluation/measure_v1_baseline.py`, `evaluation/offline_shims.py`, `evaluation/stub_vlm.py` | V1 baseline | ⚠️ **REOPENED 2026-07-26** — the run installs `offline_shims` + `stub_vlm` before executing, so 1.00/0.17/0.29 is the output of a hardcoded regex (`stub_vlm.py:34-39`), **not a measured model run**. Precision 1.00 is true by construction. Cost is `elapsed × 0.5`, not tokens. Per §1 this must be a real measurement before "V2 is better" is a fact. |
| P0.6 | `.github/workflows/ci.yml` | CI pipeline (lint, typecheck, schema-validation, unit-tests, import-linter) | ✅ **hardened 2026-07-26** — real import-linter contracts (was grep), mypy on whole tree (was `domain/` only), `--cov-fail-under=95` on validators (was unenforced) |
| P0.7 | `evaluation/golden_set/generator.py`, `evaluation/measure_v2.py`, golden set manifests | Golden-set generator + evaluation harness | ✅ **2026-07-26 session 3** — 200 docs / 30 clusters generated deterministically; §6 harness measures per-category P/R/F1 and gate table. Remaining gap: corpus is synthetic-only (no real anonymized docs, scans, or handwriting — §6 composition also asks for those). |
| P0.8 | `tests/conftest.py`, `tests/validators/test_*.py`, `tests/domain/test_*.py` | Test infrastructure + fixtures + initial tests | ✅ |

## Milestone 1 — Thin Slice (Vertical Slice)

**Goal:** prove the core thesis end-to-end: deterministic Python math over VLM extraction emits evidence-backed findings with stable fingerprints. Out of scope for M1: routing detail, governance, multi-vendor adjudication, correlation.

| Step | File(s) | Action | Status |
|------|---------|--------|--------|
| M1.1 | `audit_v2/domain/finding_generator.py` | `make_finding_from_result()` — CheckResult → Finding with `decision_fingerprint = sha256(ruleset\|prompt\|model\|extractor\|document_hash)` | ✅ |
| M1.2 | `audit_v2/domain/catalog_loader.py` | `load_catalog()` — parse `contracts/check_catalog.yaml` → `CheckCatalog` | ✅ |
| M1.3 | `audit_v2/orchestration/workflows.py` | Wire `CheckRunner` + `make_finding_from_result` into `AuditWorkflow.run`; emit `findings` on `AuditWorkflowOutput` | ✅ |
| M1.4 | `tests/test_finding_generator.py` | 4 tests: PASS emission, FAIL with evidence/delta, fingerprint stability, fingerprint changes with ruleset | ✅ |
| M1.5 | `tests/test_thin_slice.py` | 2 tests: golden invoice detects 3 deterministic FAILs (line/subtotal/tax-rate), consistent invoice emits 0 fails | ✅ |
| M1.6 | `tests/test_workflow_thin_slice.py` | 3 tests: real golden-PDF end-to-end pipeline, missing-doc → FAILED, encrypted-PDF → QUARANTINED_ENCRYPTED | ✅ |

## Phase 1 — Scope and Check Catalog

| Step | File(s) | Action | Status |
|------|---------|--------|--------|
| P1.1 | `contracts/check_catalog.yaml` | Machine-readable check catalog — **29 checks** across 8 categories, 4 doc types | ✅ |
| P1.2 | `audit_v2/domain/models.py` | Pydantic domain models — ProvenancedValue, Coverage, LineItem, Finding, CheckCatalog, etc. | ✅ |
| P1.3 | `Makefile` | Build automation: dev, test, lint, typecheck, validate-schemas, baseline-v1 | ✅ |
| P1.4 | `audit_v2/domain/validators/{arithmetic,rollforward,sequence,threshold,temporal,reference_integrity,format_completeness,duplicate}.py` | Validators, 8 modules | ✅ **2026-07-26** — 22 real, 6 corpus-level SKIPs (Phase 7), 1 model_assisted (Phase 8). 99% branch coverage. Prior "1 real, 7 stubs" was stale. |
| P1.5 | `audit_v2/gateway/vlm_gateway.py`, `audit_v2/orchestration/workflows.py` | VLM gateway stub + workflow | ⚠️ Gateway `extract()` returns `"{}"` — no SDK, no auth, no network. Workflow is a plain Python class, **not Temporal**. Prior "Temporal workflow stub ✅" overstated this. |

## Phase 2 — Governance and Controls (deferred)

**Status:** ⏳ **Not yet implemented.** Listed here to track what remains.

| Step | File(s) | Action | Status |
|------|---------|--------|--------|
| P2.1 | `audit_v2/persistence/rls.py` | Permission matrix + Postgres RLS policies | ⏳ |
| P2.2 | `audit_v2/persistence/audit_log.py` | Immutable hash-chained audit log | ⏳ |
| P2.3 | `audit_v2/persistence/models.py` | Data retention policies + scheduled job | ⏳ |
| P2.4 | `audit_v2/gateway/pii_redactor.py` | PII classification + redaction before model calls | ⏳ |
| P2.5 | — | Data residency region pinning per tenant | ⏳ |
| P2.6 | — | Model governance register + approved-model table | ⏳ |
| P2.7 | — | Separation of duties in permission matrix | ⏳ |

**Why deferred:** Governance controls are required before real tenant data can be processed, but ingestion and validation can be built in parallel per the M1 build order (§10).

### 2026-07-27 (session 4) — M2.2 Postgres + RLS shipped, V1 baseline re-measured

- **M2.1 NVIDIA baseline completed** — 200-doc run on `google/diffusiongemma-26b-a4b-it` via NVIDIA API.
  201/201 successful, avg 3.99s latency, cost ~₹2/doc. Precision 0.94 / Recall 0.63 / F1 0.56
  (`evaluation/baselines/v1.json`). P0.5 gate closes.
- **M2.2 Postgres + RLS** — `schema.py` extended with `findings` table, `app_user`
  non-superuser role (RLS bypasses superusers), `ENABLE ROW LEVEL SECURITY` + FORCE on
  all 3 tenant-scoped tables. `db.py` (connect/apply_schema/tenant_session),
  `PostgresDocumentStore`, `FindingStore` implemented. Three bugs found and fixed:
  `SET LOCAL` param mismatch, column name mismatches in `finding_store.py`, superuser
  bypassing RLS. 13/13 contract tests passing (Memory + Postgres parametrized),
  including cross-tenant RLS isolation and `information_schema` table enumeration.
  Docker Desktop confirmed working on this machine.
- **Total tests:** 328 → 328 (all green).

## Phase 3 — Ingestion Pipeline

| Step | File(s) | Action | Status |
|------|---------|--------|--------|
| P3.1 | `audit_v2/domain/models.py` | Add `QUARANTINED_ENCRYPTED`, `QUARANTINED_MALWARE` to DocumentStatus enum | ✅ |
| P3.2 | `audit_v2/persistence/schema.py`, `audit_v2/persistence/db.py`, `audit_v2/ingestion/document_store.py`, `audit_v2/persistence/finding_store.py` | DDL for `documents`, `reconciliation_log`, `findings` tables + RLS + PostgresDocumentStore + FindingStore + db helpers | ✅ **2026-07-27** — `findings` table added, `app_user` non-superuser role, all DDL idempotent, RLS enforced via FORCE + tenant_session GUC. **Bugfixes:** SET LOCAL cannot use `%s` params; finding_store column names mismatched schema; superuser bypasses RLS — fixed by creating `app_user` role. |
| P3.3 | `audit_v2/ingestion/__init__.py` | Ingestion module init | ✅ |
| P3.4 | `audit_v2/ingestion/document_store.py` | Abstract `DocumentStore` interface + `MemoryDocumentStore` + `PostgresDocumentStore` implementations | ✅ **2026-07-27** — Postgres variant added |
| P3.5 | `audit_v2/ingestion/dedup.py` | Content-hash computation (`sha256`) + dedup check | ✅ |
| P3.6 | `audit_v2/ingestion/pdf_utils.py` | PDF validation (page count ≤ 500, file size ≤ 100 MB, MIME types, encrypted PDF detection) + text-layer detection using PyMuPDF | ✅ |
| P3.7 | `audit_v2/ingestion/reconciliation.py` | Reconciliation: `accepted = completed + quarantined + failed + in_flight` | ✅ |
| P3.8 | `audit_v2/orchestration/activities.py` | Activity functions: validate_document, check_dedup, process_pdf_pages, transition_document | ⚠️ Plain synchronous functions — **no `@activity.defn`, no retry policy, no timeouts**. Prior "Temporal activity functions" was inaccurate. |
| P3.9 | `audit_v2/orchestration/workflows.py` | Real `AuditWorkflow.run()` implementing the full ingestion state machine | ✅ |
| P3.10 | `tests/test_ingestion.py` | 24 tests covering state machine transitions, content-hash dedup, document validation, reconciliation | ✅ |

## Phase 4 — Document Extraction (M1 thin slice — partial)

> Phase 4 deliverables overlap with the **Milestone 1 — Thin Slice** section above. The M1 rows capture the *emit-finding-side* proof; Phase 4 captures the *extractor-side* infrastructure already present. They are tracked together in spirit, separately in code.

| Step | File(s) | Action | Status |
|------|---------|--------|--------|
| P4.1 | `audit_v2/extraction/parser.py` | Locale-aware amount/date parsing, GSTIN/HSN/IFSC validation, PO ref extraction | ✅ |
| P4.2 | `audit_v2/extraction/base.py` | `BaseExtractor` ABC with extract/extract_header/extract_line_items/extract_tax_lines/get_coverage | ✅ |
| P4.3 | `audit_v2/extraction/text_extractor.py` | `TextExtractor` — PyMuPDF page text + bbox extraction, text-layer detection | ✅ |
| P4.4 | `audit_v2/extraction/invoice_extractor.py` | `InvoiceExtractor` — regex patterns for header fields, line items, tax lines | ✅ |
| P4.5 | `audit_v2/extraction/confidence.py` | `compute_field_confidence` (text-layer/VLM/agreement) + `agreement_score` | ✅ |
| P4.6 | `tests/test_extraction.py` | 51 tests for parser, base, text_extractor, invoice_extractor, confidence | ✅ |
| P4.7 | `audit_v2/orchestration/activities.py` | Wire `extract_document` + `normalize_document` activities | ✅ **fixed 2026-07-26** — `normalize_document` was previously a no-op that was never called; now wired. `extract_document` no longer hardcodes `InvoiceExtractor` — it uses the classifier. |
| P4.8 | `audit_v2/orchestration/workflows.py` | Wire extraction/normalization into `AuditWorkflow.run()` — transitions through EXTRACTED/NORMALIZED | ✅ |
| P4.9 | `audit_v2/extraction/po_extractor.py` | `POExtractor` — regex patterns for PO header fields (po_number, vendor, dates, total), line items, no tax lines | ✅ |
| P4.10 | `tests/test_po_extractor.py` | 12 tests for PO extractor: header fields, line items, full document, provenance, missing fields, variants, tax lines | ✅ |
| P4.11 | `audit_v2/extraction/classifier.py` | Register POExtractor in EXTRACTOR_REGISTRY | ✅ |
| P4.12 | `audit_v2/extraction/delivery_challan_extractor.py` | `DeliveryChallanExtractor` — regex patterns for DC header fields (dc_number, vehicle_number, po_reference, dates), line items (desc, hsn, qty, unit), no tax lines | ✅ |
| P4.13 | `tests/test_dc_extractor.py` | 7 tests for DC extractor: header, line items, full document, provenance, missing fields, no tax lines | ✅ |
| P4.14 | `audit_v2/extraction/classifier.py`, `tests/test_classifier.py` | Register DC in EXTRACTOR_REGISTRY, update DC registry test | ✅ |
| P4.15 | `audit_v2/extraction/grn_extractor.py` | `GRNExtractor` — regex patterns for GRN header fields (grn_number, po_reference, vendor_name, date), line items (desc, hsn, ordered/received/rejected qty), no tax lines | ✅ |
| P4.16 | `tests/test_grn_extractor.py` | 8 tests for GRN extractor: header, line items, full document, provenance, missing PO, missing inspected_by, no tax lines, empty data | ✅ |
| P4.17 | `audit_v2/extraction/classifier.py`, `tests/test_classifier.py` | Register GRN in EXTRACTOR_REGISTRY, update GRN registry test | ✅ |

## Phase 5 — Routing Engine

| Step | File(s) | Action | Status |
|------|---------|--------|--------|
| P5.1 | `audit_v2/routing/__init__.py` | Empty module init | ✅ |
| P5.2 | `audit_v2/routing/models.py` | RoutingRule + RoutingDecision Pydantic models | ✅ |
| P5.3 | `contracts/routing_rules.yaml` | 4 routing rules (INV, PO, DC, GRN) | ✅ **rewritten 2026-07-26** — prior version referenced 5 check IDs absent from the catalog (`CHK-FORMAT-FIELDS-001`, `CHK-DUP-001`, `CHK-THRESH-MATERIALITY-001`, `CHK-SEQ-DATE-001`, `CHK-SEQ-GAP-001`) |
| P5.4 | `audit_v2/routing/engine.py` | `resolve()` + `load_rules()` — deterministic doc_type/value_band/policy → check set | ✅ **hardened** — package-relative path (was cwd-relative), rules cached (was re-parsed per call) |
| P5.5 | `tests/test_routing.py`, `tests/test_catalog_registry_consistency.py` | Routing tests + catalog/registry/routing consistency (13 new) | ✅ |
| P5.6 | `audit_v2/orchestration/workflows.py` | Wire routing into `AuditWorkflow.run()` | ✅ **fixed 2026-07-26** — routing result was previously **discarded** in favour of a hardcoded `["CHK-ARITH-LINE-001"]`. Golden invoice: 1 check → **25**. |

---

## Summary

**As of 2026-07-27, end of session M2.5.**

| Metric | Count | Δ this session |
|--------|------:|----------------|
| Checks catalogued | 29 | — |
| Deterministic checks | 28 (96.5%) | — |
| Checks actually executed on an invoice | **25** | **+24** (routing was discarded; only 1 ran) |
| Doc types covered | 4 (invoice, PO, delivery_challan, GRN) | — |
| Validator functions | 30 — 22 real, 6 corpus SKIP (Phase 7), 1 model_assisted (Phase 8), 1 helper | reclassified |
| Validator branch coverage | **99%** | +35 pts (was 64%) |
| Test files | 21 | +5 |
| Test cases | **308** | +122 |
| Architecture contracts | 3 kept (incl. domain purity) | new — replaced `grep` |
| mypy | clean, 46 files, whole tree | was `domain/` only |

### Gate status (`PHASES_V2.md` §6)

Measured on the 200-doc synthetic golden set (`evaluation/baselines/v2.json`, seed 42):

| Gate | Current | Target | Pass? |
|------|--------:|-------:|:-----:|
| Arithmetic check precision | **1.00** (90 TP, 0 FP over 200 docs) | 1.00 | ✅ |
| Arithmetic check recall | **1.00** (0 FN) | ≥ 0.98 | ✅ |
| Overall finding precision | **1.00** | ≥ 0.90 | ✅ |
| Overall finding recall | **1.00** | ≥ 0.85 | ✅ |
| Injection corpus PASS rate | **0** (10 techniques, 27 tests) | 0 | ✅ |
| Determinism (repeat-run agreement) | **1.00** exact over 10 runs | ≥ 0.98 | ✅ |
| Validator branch coverage | 99% | ≥ 95% | ✅ |
| Domain-purity / import contracts | enforced in CI | ✓ | ✅ |
| Security injection recall | **1.0** (10/10 detected) | 1.0 | ✅ |
| Extraction field F1 | **0.183** (164 TP / 1243 FN) | ≥ 0.95 | ⏳ |
| Confidence calibration (ECE) | **0.00** (all deterministic) | ≤ 0.05 | ✅ |
| Cost per document | not measurable — no real model calls | ≤ ₹4.00 | ⏳ |

> **Caveat on the 1.00s.** The corpus is synthetic and rendered by the same
> layout family the extractors were tuned on. These numbers prove the
> deterministic engine is sound end-to-end; they do NOT prove extraction
> robustness on real-world documents (scans, handwriting, unseen layouts) —
> §6 composition requires adding those before this can be called ship-ready.

> **Note on the earlier "recall 0.50" figure.** It was attributed to Phase 7
> cascade work. The actual cause was that routing was discarded and only one
> check ever ran (`shortcomings.md` §11.1).

### M2 items

1. ~~**V1 baseline (P0.5).**~~ ✅ Done 2026-07-27 — NVIDIA DiffusionGemma 26B.
2. ~~**Golden set 1→200 (P0.7).**~~ ✅ Done 2026-07-26.
3. ~~**Temporal integration.**~~ ✅ Done 2026-07-26 session 3b.
4. ~~**Postgres + RLS.**~~ ✅ Done 2026-07-27.
5. ~~**M2.3 chaos test.**~~ ✅ Done 2026-07-27.
6. ~~**M2.4 harness gaps.**~~ ✅ Done 2026-07-27.
7. **M2.5 injection golden set.** ✅ Done 2026-07-27 — 10 injection PDFs + `security_injection` gate at 1.0.

**Session 2026-07-27 late — M2.3 (chaos) + M2.2 residual**
- `audit_v2/persistence/__init__.py` populated with exports.
- `worker.py`: `_build_store()` selects Postgres/Memory based on env.
- `tests/chaos/test_worker_kill.py`: 3 tests (batch, restart, unique finding
  pairs), all passing in 19s.
- `.env` updated with `AUDIT_PG_DSN`, `AUDIT_PG_APP_DSN`, `TEMPORAL_*`.
- docker-compose Temporal section updated but disabled pending config mount.
- `chaos` marker registered in `pyproject.toml`.
 **Session 2026-07-27 — M2.4 (harness gaps)**
- `audit_v2/orchestration/workflows.py`: added `document: ExtractedDocument | None` to `AuditWorkflowOutput`, populated on success path.
- `evaluation/measure_v2.py`: implemented `_decimal_equal()`, `score_extraction()` (compares `expected_fields`/`expected_lines` from golden manifest vs extracted document), wired `compute_ece()` + `determinism_score()` via second pass. Added extraction F1 (0.0 — genuine: extraction needs work), ECE (0.0 — all deterministic), determinism (1.0 — perfect replay) gates.
- `shortcomings.md` §12: deprecated `compute_ece`/`determinism_score` callers gap.
- `docs/superpowers/specs/2026-07-27-m2-4-harness-gaps-design.md`: design doc.
- `docs/superpowers/plans/2026-07-27-m2-4-harness-gaps.md`: implementation plan.
- **Session 2026-07-27 — M2.5 injection golden set**
- `evaluation/golden_set/generator.py`: added `expected_status` field to `GeneratedDoc`, `INJECTION_CORPUS` (10 injection techniques), `generate_injection_pdf()` function, `--include-injection` flag.
- `evaluation/measure_v2.py`: added security injection scoring (document-level status comparison, not per-check findings) + `security_injection` gate (recall=1.0, PASS).
- Generated 10 injection PDFs with manifests expecting `QUARANTINED_SECURITY` + 200 regular golden set docs. All 10 detected by the workflow, `security_injection` gate PASS at 1.0. All other gates still PASS (arithmetic 1.0/1.0, overall 1.0/1.0, determinism 1.0, ECE 0.0). Extraction F1 remains at 0.183 (genuine gap).
- `docs/superpowers/specs/2026-07-27-m2-5-injection-golden-set-design.md`: design doc.
- `docs/superpowers/plans/2026-07-27-m2-5-injection-golden-set.md`: implementation plan.
- **Next:** M3 real/scanned/adversarial document composition.
