# Codebase Shortcomings

> **Audit refresh 2026-07-26 (session 3).** Sections 1–10 below were written
> earlier and several are now **stale**; corrections are marked inline. See
> §11 for what this session fixed and §12 for what genuinely remains.

## 1. Extraction Layer — Fragile Regexes

| Issue | Location | Impact |
|-------|----------|--------|
| Regexes match exact Indian GST labels ("Seller:", "Buyer:", "CGST", "SGST") | `invoice_extractor.py:27-64` | Non-Indian or differently-formatted invoices produce zero output silently |
| Line-item table assumes rigid `\| # \| Description \| HSN \| Qty \| Rate \| Amount \|` structure | `invoice_extractor.py:66-80` | Column order/name/separator variations cause silent line-item loss |
| Line-item descriptions must start with `[A-Za-z]` | `invoice_extractor.py:74` | "3D Printer", "₹50 item" etc. are silently skipped |
| `TABLE_END_MARKERS` stops on any line starting with "Total" or "Subtotal" | `invoice_extractor.py:209-212` | A description containing "Total" terminates the table early |
| Unparseable line items silently dropped (no log, no error) | `invoice_extractor.py:243-244` | `continue` with zero observability |
| Coverage always hardcoded to `pages_total=1, pages_examined=1` | `invoice_extractor.py:126-131` | ~~Fixed — multi-page coverage uses real page count from TextExtractor (M1b)~~ |
| No `\r\n` handling | `invoice_extractor.py:218` | ~~Fixed — now uses `splitlines()` instead of `split("\n")` (M1b)~~ |
| Taxable value hardcoded to `"0"` in all tax lines | `invoice_extractor.py:274,284,302` | CHK-ARITH-TAX-\* checks cannot validate correctly |
| Only 4 currency symbols supported in regex | `invoice_extractor.py:57,84,89,94` | `¥`, `₩`, `₽`, etc. cause parse failures |
| VLM fallback for textless/scanned PDFs is deferred — extractor silently returns no text | `invoice_extractor.py:108-114` | Users see empty extraction with no warning |

## 2. Validators — ~~23 of 24 Check Functions Are No-Ops~~ **STALE**

> **Correction (2026-07-26):** this section is out of date. 22 of 29 catalog
> checks now have real logic; 6 are deliberate corpus-level SKIPs (Phase 7) and
> 1 is model_assisted (Phase 8). Validator branch coverage is **99%**. The rows
> below are retained only for history.

| Issue | Location | Impact |
|-------|----------|--------|
| ~~Only `check_line_total` is implemented~~ | `validators/arithmetic.py:7` | Fixed — 7 arithmetic checks implemented |
| ~~7 of 8 validator modules always return `CheckResult.passed()`~~ | — | Fixed — only `duplicate` returned a false PASS; now SKIPs |
| ~~No validator module uses `logging`~~ | — | Partially fixed — dispatcher logs; validators remain pure by design |
| `CheckContext` holds only one document | `models.py` | **Still true.** Blocks REF-QTY-001/002, SEQ-*, DUP-* (Phase 7) |
| ~~Domain model has no `subtotal` or `discounts` field~~ | `models.py` | Stale — `subtotal`, `discount_amount`, `discount_percentage` all exist |

## 3. Orchestration — Not Actually Temporal

| Issue | Location | Impact |
|-------|----------|--------|
| `AuditWorkflow` is a plain Python class, not a Temporal workflow | `workflows.py:35` | No durable execution, no replay, no restart safety — despite AGENTS.md claiming Temporal |
| No `@workflow.defn`, no `@activity.defn` decorators | `workflows.py`, `activities.py` | Zero integration with the Temporal dev stack in docker-compose |
| No retry policies, timeouts, or saga/compensation | `activities.py`, `workflows.py` | Transient failures (network, DB) cause immediate workflow failure |
| `async def run` but all activities are synchronous | `workflows.py:39` | `async` provides no benefit and misleads callers |
| `normalize_document` returns input unchanged | `activities.py:108-109` | NORMALIZED state transition does nothing |
| `process_pdf_pages` returns raw `dict` instead of typed dataclass | `activities.py:57` | Type checkers cannot validate dict keys — inconsistent with all other activities |
| Document can reach READY with no extraction if data is None | `workflows.py:130-135` | Document marked ready without any processing |

## 4. Persistence — Not Persisted

| Issue | Location | Impact |
|-------|----------|--------|
| `AuditWorkflow` defaults to `MemoryDocumentStore` | `workflows.py:37-38` | All state lost on restart. No production durability |
| `schema.py` DDL defined but never imported or executed | `persistence/schema.py:1-42` | Database schema exists only as text — no initialization path |
| SQL columns don't match domain model fields | `persistence/schema.py:5-23` | Columns like `pii_classes`, `residency_region` have no model equivalent; `vendor_name`, `buyer_name` have no column |
| No `findings` table defined | N/A | Where findings are stored is undefined |
| `MemoryDocumentStore` has no thread/async safety | `document_store.py:62-63,85` | Concurrent workflow executions can corrupt state or produce duplicate IDs |

## 5. No Observability

| Issue | Impact |
|-------|--------|
| Zero `logging` statements in any production module (15+ Python files) | Silent failures everywhere: skipped line items, missing fields, empty VLM results, validators returning PASS without checking — none logged |
| Zero OpenTelemetry spans/traces despite `opentelemetry-api` and `opentelemetry-sdk` in dependencies | No distributed tracing, no performance monitoring |
| Zero metrics (no counters, histograms, timing) | No insight into throughput, error rates, or latency |
| No health check endpoint | Cannot be deployed behind a load balancer or orchestrator |

## 6. No Configuration or Secrets Management

| Issue | Impact |
|-------|--------|
| No config classes, no `python-dotenv`, no env var reads in production code | Database URLs, API keys, rate limits, timeouts — all must be hardcoded |
| `GeminiGateway` has no API key or credential management | Any actual model call would fail to authenticate |
| No rate limiting or token budget | No protection against runaway model costs |

## 7. Test Coverage Gaps

| Gap | Location | Impact |
|-----|----------|--------|
| Tests duplicate production logic instead of importing it | `test_ingestion.py:104-165,270-287,325-327` | Tests verify test code, not production code. Changing MAX_PAGE_COUNT from 500→1000 doesn't break tests |
| `TestDocumentStateTransitions` tests local `_can_transition` not `transition_document` from activities | `test_ingestion.py:21-101` | Production `transition_document` has zero test coverage |
| PDF tests silently skip when sample PDF missing | `test_extraction.py:349-350,374-376` | Tests don't run in CI if sample files not in repo |
| No test for malformed/unparseable documents | Missing | No test verifies behavior on garbled input |
| No test for extract() with images | Missing | Image extraction path is untested |
| `CheckContext`, `ExtractedDocument`, `Finding`, `make_fingerprint` have zero test coverage | Missing | Core data structures and the fingerprint function are untested |
| No test that catalog check_ids have corresponding validator implementations | Missing | 28 of 29 checks being no-ops is invisible to CI |
| No test that check `inputs` fields exist as domain model fields | Missing | `discounts` referenced but doesn't exist — no test catches it |
| No integration tests (workflow, extraction pipeline, validator dispatch) | Missing | E2E behavior untested |
| No property-based tests despite `hypothesis` in dev deps | Missing | `parse_amount` with diverse inputs untested |
| No concurrency, async, or schema tests | Missing | Thread safety, async behavior, persistence all untested |

## 8. V1 Baseline Empirically Confirms B1/B3/B4 (2026-07-26)

The V1 baseline was measured on `doc_gold_inv_001` (`INV-2026-0715_NewTech_Solutions.pdf`):

- **Macro Precision: 1.00** (1/1 reported FAILs were correct — line-item arithmetic)
- **Macro Recall: 0.17** (1/6 expected FAILs detected — subtotal, tax-rate, tax-calc, grand-total, amount-in-words all missing)
- **Macro F1: 0.29**

This empirically confirms three of the seven blocking defects noted in `PHASES_V2.md` §0.1:

| Defect | Empirical Evidence |
|--------|--------------------|
| **B1** (arithmetic delegated to LLM) | V1's `R003` prompt instructs Gemini to do math inline, so it audits only the line-item rule and skips subtotal/tax/grand-total even though they exist in `checklist.md`. Recall 0.17 is the direct consequence. |
| **B3** (money as `float`) | V2 already uses `Decimal` everywhere; baseline confirms the gap. |
| **B4** (silent 10-page truncation) | V1's `MAX_PDF_PAGES = 10` silently caps examination. The golden doc has 18 pages; pages 11-18 are never audited. |

This number (`v1.json`) is the single quantitative target V2 must beat at every milestone.

## 9. M1 Vertical Slice Verified (2026-07-26)

The M1 vertical-slice thesis — *deterministic Python math over VLM extraction emits evidence-backed findings with stable fingerprints* — is proven end-to-end:

- `audit_v2/domain/finding_generator.py::make_finding_from_result` converts a `CheckResult` into a `Finding` with `decision_fingerprint = sha256(ruleset|prompt|model|extractor|document_hash)`.
- `audit_v2/orchestration/workflows.py::AuditWorkflow.run` wires `CheckRunner` + `make_finding_from_result` into the pipeline.
- `tests/test_workflow_thin_slice.py` runs the real golden PDF (`INV-2026-0715_NewTech_Solutions.pdf`) through `AuditWorkflow` end-to-end and verifies the workflow reaches `READY` with findings emitted.
- A consistent (non-defective) invoice produces **zero arithmetic findings** — the entire reason V2 exists.
- `tests/test_thin_slice.py::test_thin_slice_detects_deterministic_stated_arithmetic_failures` proves the three deterministic checks (`CHK-ARITH-LINE-001`, `CHK-ARITH-SUBTOTAL-001`, `CHK-ARITH-TAX-001`) fire correctly on stated numbers from a deliberately-broken invoice.

### Known gaps still remaining after M1

| Gap | Phase it belongs to |
|-----|---------------------|
| Golden manifest expects `CHK-ARITH-GRAND-001` and `CHK-ARITH-TAX-002` to FAIL — but the deterministic validators PASS them because subtotal + tax == grand-total is internally consistent even on a defective invoice. Resolving the *correct* grand total requires cascaded recomputation, not stated-number arithmetic. | Phase 7 — three-way correlation / adjudication |
| Golden manifest expects `CHK-FORMAT-WORDS-001` to FAIL. The check is model_assisted (`determinism: model_assisted` in catalog), so it is intentionally skipped by the deterministic dispatcher. | Phase 8 — adjudication |
| 7 of 8 validator modules remain stubbed (`duplicate`, `format_completeness`, `reference_integrity`, `rollforward`, `sequence`, `temporal`, `threshold`). | Phase 6 completion |
| No Temporal integration — `AuditWorkflow` is a regular Python class | Phase 0 (Temporal dev stack) + M2 |
| Golden set is 1 manifest of the ≥200 required. | ✅ **Done session 3** — 200 docs / 30 clusters via `evaluation/golden_set/generator.py` |

## 10. Cross-Cutting

| Issue | Location | Impact |
|-------|----------|--------|
| `FailureClass` enum defined but never used | `models.py:67-73` | Transient vs poison vs logic errors are indistinguishable |
| 6 dead functions defined but never called | `normalize_locale`, `validate_ifsc`, `is_duplicate`, `reconcile`, `normalize_document`, `make_fingerprint` | Code rot — indicates incomplete refactoring |
| `make_fingerprint` defined but decision fingerprints never constructed | `models.py:296-300` | AGENTS.md mandates fingerprints; no code produces them |
| No error classification — every failure raises `ValueError` or bare `Exception` | Throughout | Retriable errors and programming bugs are indistinguishable |
| No serialization layer | Throughout | Domain models have no `.to_json()` or `.to_dict()` — no path from memory to disk/wire |
| `LineItem.expected_total` hardcodes 2-decimal rounding | `models.py:159-162` | JPY, KWD, and zero-decimal currencies produce wrong expected totals |
| `ProvenancedValue.decimal_value` raises uncaught `Decimal` exception on non-numeric values | `models.py:87` | A `value` of `"N/A"` crashes the process |
| Silent PyMuPDF import failure returns empty data with no warning | `text_extractor.py:8-11`, `pdf_utils.py:41-42,56-57` | ~~Fixed — now raises RuntimeError with logging warning (M1b)~~ |
| Broad `except Exception` in multiple modules | `text_extractor.py:15-16`, `pdf_utils.py:43-44,58-59`, `workflows.py:137-143` | ~~Fixed in `workflows.py` and `validation.py` — `KeyboardInterrupt`/`SystemExit`/`MemoryError` now re-raised (session 2)~~ |

---

## 11. Fixed in session 2 (2026-07-26)

### 11.1 Routing was computed and discarded — **the single highest-impact bug**

`workflows.py` called `resolve()` and then ran a hardcoded
`catalog_check_ids = ["CHK-ARITH-LINE-001"]`, so the pipeline executed **1 of 29
checks**. The routing result was never used. shortcomings.md §9 attributed the
resulting recall gap to "Phase 7 cascade work"; that diagnosis was wrong.

Compounding this, `contracts/routing_rules.yaml` referenced **five check IDs that
do not exist in the catalog** (`CHK-FORMAT-FIELDS-001`, `CHK-DUP-001`,
`CHK-THRESH-MATERIALITY-001`, `CHK-SEQ-DATE-001`, `CHK-SEQ-GAP-001`), so naively
wiring routing in would have skipped nearly everything.

Fixed: rules rewritten against real check IDs and `applies_to`; the workflow now
selects deterministic checks applicable to the classified doc type and honours
`routing_decision`. **Golden invoice went from 1 check to 25.**

### 11.2 Extraction corrupted table columns

`text_extractor.py` joined PyMuPDF spans with `""`, fusing adjacent table cells:
HSN `8471` + qty `2` + rate `45,000.00` became `8471245,000.00`. This produced
garbage line items and false arithmetic failures on every table-formatted
invoice. Spans are now tab-joined, preserving column boundaries.

Also fixed in the invoice extractor: `grand_total` matched a GST-table row rather
than "Grand Total"; `subtotal` and `bank_details` were never extracted despite
`SUBTOTAL_RE` existing; `TAX_LINE_RE` could not match `Add: CGST @ 9%<tab>Rs.
12,042.00`, so **zero tax lines were extracted**; `taxable_value` was hardcoded
to `"0"`, making CHK-ARITH-TAX-002 unverifiable.

### 11.3 Fabricated GST rate table

`_prescribed_rate_for_hsn` invented HSN→rate mappings from digit prefixes
(`startswith("99") → 0.25`, else prefix buckets, fallback 28) and paired tax
lines to HSNs by **positional index**. This emitted confidently wrong tax
findings. Removed: `CHK-ARITH-TAX-001` now verifies only what is deterministically
checkable — that the charged rate is a legal GST slab. Per-HSN rate correctness
needs the CBIC schedule and must be escalated, not guessed.

`GST_SLAB_RATES` also omitted the CGST/SGST component halves, so a legitimate
18% slab levied as 9%+9% failed. Now included.

### 11.4 Checks that reported compliant without checking

- `duplicate.check_duplicate_document` returned unconditional **PASS**. Now SKIPs.
- `validation.py` turned validator exceptions into **FAIL** findings, making a
  code bug indistinguishable from a document defect (violates §3.3 `LOGIC`).
  Now `NEEDS_REVIEW` + `logger.exception`.
- An unregistered check_id silently SKIPped. Now `NEEDS_REVIEW` + `logger.error`.
- `check_discount_cap` compared a *relative* tolerance of subtotal against a
  *percentage-point* delta, making it unfailable on large invoices.
- `check_hsn_code` rejected 4-digit HSN headings, which are legal under the
  turnover-slab rules.

### 11.5 Coverage integrity (§3.5) was not enforced

A document with incomplete page coverage could still reach `READY`. The workflow
now emits `INCOMPLETE` when `coverage_complete` is false.

### 11.6 Security — §5 had zero implementation

Added `audit_v2/security/injection_detector.py`: instruction-pattern detection,
plus invisible-text detection (zero-size fonts, off-canvas text, near-white text
that is *not* backed by a dark fill — the naive colour check false-positived on
white-on-dark table headers in the real golden invoice). Wired into the workflow
as `QUARANTINED_SECURITY` / `FailureClass.POLICY`.

Red-team corpus added: 10 injection techniques + 4 benign controls, all asserted.

### 11.7 Fingerprint was not content-addressed

`_document_hash` included `document_id`, so the same content ingested twice
produced different fingerprints — defeating the §8 fingerprint-keyed cache. It
also omitted `subtotal`, `grand_total`, discounts, dates and GSTIN, so materially
different documents could share a fingerprint. Now hashes content only, across
all verdict-relevant fields.

### 11.8 Other

- `normalize_document` was never called; now wired.
- `extract_document` hardcoded `InvoiceExtractor`; now uses the classifier.
- `LineItem.expected_total` hardcoded 2-decimal rounding (wrong for JPY/KWD);
  now takes a currency exponent, threaded from `CheckContext`.
- `ProvenancedValue.decimal_value` raised a bare `InvalidOperation` on `"N/A"`;
  now a clear `ValueError` naming the field.
- `Finding.currency` was declared but never populated.
- `pii_redactor` GSTIN pattern `[ZYZ5]` typo (duplicate `Z` in char class).
- `load_rules` used a cwd-relative path and re-parsed YAML on every `resolve()`
  call; now package-relative and cached.

### 11.9 Test and CI gates

| Gate | Before | After |
|------|--------|-------|
| Tests | 186 | **308** |
| Validator branch coverage | 64% (6 tests, 30 functions) | **99%** (77 tests) |
| `--cov-fail-under` | absent | **95, enforced** |
| import-linter | `grep -r "from app"` | **real contracts, 3 kept** |
| Domain-purity contract | none | **enforced** (structural guard against B1) |
| mypy | `--strict` on `domain/` only | **whole tree, clean (46 files)** |
| Property-based tests | none (`hypothesis` unused) | **6** |
| Injection corpus | none | **27 tests, hard gate** |
| Determinism gate | none | **4 tests, exact agreement** |
| Catalog↔registry↔routing consistency | none | **13 tests** |

---

## 12. What genuinely remains

| Gap | Phase / milestone |
|-----|-------------------|
| ~~**Not Temporal.**~~ ✅ **Done session 3 + M2.3 (2026-07-27)** — `AuditDocumentWorkflow` (`@workflow.defn`), 7 activities (`@activity.defn`), worker entrypoint, 5+3 tests. `worker.py` `_build_store()` auto-detects `PostgresDocumentStore` when `AUDIT_PG_DSN` is set. Chaos test (`tests/chaos/test_worker_kill.py`, @chaos marker) covers batch concurrency (10 docs), worker restart cycle, and (document_id, check_id) uniqueness — all pass in 19s. **Remaining ceilings:** PDF bytes travel through workflow history (needs blob store); real docker-compose Temporal server unwired (v1.31+ needs config file mount); `FindingStore.insert` not called in `persist_results_activity`. | M2 |
| ✅ **Postgres persists everything (2026-07-27).** `PostgresDocumentStore` + `FindingStore` + `documents`/`findings`/`reconciliation_log` tables with `ENABLE ROW LEVEL SECURITY` + `FORCE`. Schema applied on worker start. 13 contract tests pass. | done |
| ✅ **RLS enforced (2026-07-27).** `app_user` non-superuser role. `test_every_tenant_table_has_rls` enumerates `information_schema` — any tenant-scoped table added without forced RLS fails CI. | done |
| **The V1 baseline is synthetic.** `measure_v1_baseline.py` installs `offline_shims` + `stub_vlm` before running; the "measured" 1.00/0.17/0.29 is the output of a hardcoded regex (`stub_vlm.py:34-39`), not a model. `estimated_cost_per_doc_inr` is `elapsed_seconds * 0.5`, not tokens. **§1 calls this the only number that makes "V2 is better" a fact — it is not yet a fact.** | M0 (reopen) |
| ~~**Golden set is 1 document**~~ ✅ **Done session 3** — 200 docs / 30 vendor clusters (140 INV, 30 PO, 15 DC, 15 GRN; 74 with seeded defects from a 9-defect taxonomy). Measured on it: arithmetic P/R **1.00/1.00**, overall P/R/F1 **1.00/1.00/1.00** (`evaluation/baselines/v2.json`). The exercise immediately caught 2 extraction bugs (phantom PO-ref regex match inside "24-port"; DC/GRN dates stored in `invoice_date` so mandatory-field checks false-alarmed). **Remaining:** corpus is synthetic-only and shares the extractors' layout family — §6 also requires real anonymized docs, poor scans, handwriting, and adversarial composition; no per-field extraction-F1 scorer; no temporal/sequence/rollforward defects seeded (cross-doc, Phase 7). | real-doc composition: M2/M3 |
| **No model integration at all.** `GeminiGateway.extract` returns `"{}"`; no SDK, no API key, no retry/cache/budget. Extraction is pure regex over PyMuPDF text. | M2/M3 |
| **Scanned and image documents always fail.** All four extractors `raise ValueError("No extractable text found")`; images pass MIME validation then hit the same path. No OCR, no VLM fallback. | M3 |
| **No observability.** Logging now exists in ~6 modules but there are still zero OpenTelemetry spans and zero metrics despite the SDK being a declared dependency. No health endpoint. | M2 |
| **No config/secrets management.** No env reads in production code, no rate limiting, no token budget. | M2 |
| **No malware scan.** `QUARANTINED_MALWARE` is an enum value no code path can set. | Phase 3 |
| **`is_encrypted_pdf` is `b"/Encrypt" in data`** — a naive substring scan that false-positives on any PDF containing those bytes in a stream. | Phase 3 |
| **Corpus-level checks remain SKIPs** (6): `CHK-SEQ-*`, `CHK-REF-QTY-001/002`, duplicate detection. `CheckContext` holds one document, so these are structurally blocked until the corpus index exists. | Phase 7 |
| `CHK-FORMAT-WORDS-001` is model_assisted and deferred. | Phase 8 |
| `MemoryDocumentStore` has no thread/async safety; `create` only increments `_counter` on the non-duplicate path, so duplicates collide on generated id. | M2 |
| `MemoryVectorStore.search` ignores both the query vector and `tenant_id` — it is not a vector search, and post-filtering by tenant would leak neighbours anyway (§3.7). | M4 |
| `pii_redactor` exists with 13 tests but **is called by nothing** — the gateway does not redact before model calls, contrary to its own docstring. | Phase 2 |
| `evaluation/metrics.py` (`compute_ece`, `determinism_score`) has no callers. No ECE calibration measurement. | M2 |
| Extraction regexes remain Indian-GST-shaped and brittle (§1 above still largely applies). Unparseable line items are still dropped silently. | M3 |
