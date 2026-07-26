# Implementation Tracker

**Project:** Multi-Model Document Audit Agent (V2)
**Plan source:** `PHASES_V2.md`
**Started:** 2026-07-25
**Current build:** 2026-07-26
**Active milestones:** M0 Foundations ✅ · M1 Thin Slice ✅ · M2 Hardening ⏳
**Approach:** Vertical Slice (per `AGENTS.md` §10, M1 is deliberately narrow and first)

---

## Build Log

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
| P0.7 | `generate_test_bill.py` (rewrite), `evaluation/metrics.py`, golden set manifests | Extended generator + evaluation harness + manifest | 🟡 **1 of ≥20** golden manifests exist (target: 200 docs / 30 clusters by M2 exit; see §6 of `PHASES_V2.md`) |
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

## Phase 3 — Ingestion Pipeline

| Step | File(s) | Action | Status |
|------|---------|--------|--------|
| P3.1 | `audit_v2/domain/models.py` | Add `QUARANTINED_ENCRYPTED`, `QUARANTINED_MALWARE` to DocumentStatus enum | ✅ |
| P3.2 | `audit_v2/persistence/schema.py` | DDL for `documents` and `reconciliation_log` tables | ⚠️ Written but **never imported or executed** — no migration runner, no connection, and **no `findings` table** |
| P3.3 | `audit_v2/ingestion/__init__.py` | Ingestion module init | ✅ |
| P3.4 | `audit_v2/ingestion/document_store.py` | Abstract `DocumentStore` interface + `MemoryDocumentStore` implementation | ✅ |
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

**As of 2026-07-26, end of session 2 (correctness audit + remediation).**

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

| Gate | Current | Target | Pass? |
|------|--------:|-------:|:-----:|
| Arithmetic check precision | 1.00 — all 3 FAILs on the golden invoice are genuine defects | 1.00 | ✅ |
| Injection corpus PASS rate | **0** (10 techniques, 27 tests) | 0 | ✅ |
| Determinism (repeat-run agreement) | **1.00** exact over 10 runs | ≥ 0.98 | ✅ |
| Validator branch coverage | 99% | ≥ 95% | ✅ |
| Domain-purity / import contracts | enforced in CI | ✓ | ✅ |
| Arithmetic check recall | not meaningfully measurable — golden set is 1 doc | ≥ 0.98 | ⏳ blocked on golden set |
| Extraction field F1 | not measured (no label set) | ≥ 0.95 header | ⏳ |
| Confidence calibration (ECE) | not measured (`compute_ece` has no callers) | ≤ 0.05 | ⏳ |
| Cost per document | not measurable — no real model calls | ≤ ₹4.00 | ⏳ |

> **Note on the earlier "recall 0.50" figure.** It was attributed to Phase 7
> cascade work. The actual cause was that routing was discarded and only one
> check ever ran (`shortcomings.md` §11.1). Recall cannot be honestly restated
> until the golden set exceeds one document.

### Blocking items before M2 can close

1. **Re-measure the V1 baseline against a real model.** The committed number is
   stub output (`shortcomings.md` §12). Until then, "V2 beats V1" is unproven.
2. **Golden set: 1 → 200 documents, 30 clusters.** Every gate above marked ⏳ is
   blocked on this. §9 lists "golden set never built" as a Critical risk.
3. **Temporal integration.** Nothing in the repo imports `temporalio`; §2's
   restart-safety NFR currently has no mechanism.
4. **Postgres + RLS.** All state is in memory; the DDL never executes; there is
   no `findings` table and no cross-tenant isolation test.
