# TrustAudit product reliability implementation plan

Prepared: 7 September 2026

Status: Proposed implementation plan. No fixes are implied by this document.

## 1. Objective and scope

Make V2 a dependable assisted audit product for invoices, purchase orders, goods receipts, and their cross-verification. Every decision must state what was checked, what could not be checked, which evidence supports it, and which version of the rules produced it. Expand autonomous clearance only after measured release gates pass.

Initial release scope: one explicitly configured currency/tax policy per transaction, identifiable suppliers and buyer entities, invoice–PO–receipt matching, duplicate detection, evidence review, and durable history. Unsupported currencies, units, document types, and transaction structures must remain unresolved rather than being silently approximated. Existing reconciliation features must retain their regression coverage; this review did not establish their production readiness.

Retain the useful foundations: Decimal validators, check catalog, provenance models, safe extraction states, review queue concepts, SQLite session traces, and existing Postgres/Temporal components. Integrate and correct them rather than build a second competing pipeline.

## 2. Findings and required outcomes

| Finding | Evidence from review | Required outcome |
|---|---|---|
| Unmatched lines can pass | Reproduced price and receipt-quantity PASS with no matching invoice item | Unmatched required lines block clearance |
| Overall pass derives from score | API uses ready document and score >= 80; review flag is separate | One authoritative decision policy independent of score |
| Wrong transaction grouping | Reproduced different suppliers sharing PO number in one cluster | Tenant/entity/supplier scoped linkage with ambiguity handling |
| Duplicate business number missed | Reproduced same printed invoice number with altered amount/date passing | Separate upload identity, business identity, and revision identity |
| Weak field grounding | Numeric grounding primarily tests page-wide number presence | Field/row/region evidence binding |
| Unavailable cross-check appears supported | Cross-check returns supported=True on unavailable/error paths | Explicit execution and outcome states |
| Benchmark hides unresolved defects | Reproduced expected FAIL emitted NEEDS_REVIEW with zero false negatives/misses | Complete expected-case accounting and separate abstention metrics |
| Confidence claims lack calibration | Evaluator supplies confidence=1.0 | Measure actual confidence or remove probabilistic claim |
| Tenant/reviewer boundaries incomplete | Global stores and unfiltered findings route; caller-supplied reviewer | Authenticated server-side identity and enforced tenant isolation |
| Operational state is volatile | Active findings, clusters, reviews and log in memory | Durable transactional operational state and recovery |

Reproductions were targeted domain/evaluator probes, not full live-OCR acceptance tests. Additional risks below are planned hardening requirements, not claims that each failure has already been reproduced.

## 3. Non-negotiable decision contract

Separate three dimensions instead of overloading one score:

- Processing: queued, running, completed, failed, cancelled.
- Audit decision: PASS, FAIL, NEEDS_REVIEW, INCOMPLETE, UNSUPPORTED.
- Review disposition: pending, confirmed, disputed, resolved, exception accepted.

Check outcomes: PASS, FAIL, NEEDS_REVIEW, NOT_APPLICABLE, NOT_RUN, ERROR. Preserve a compatibility adapter for existing SKIPPED values, but require a reason distinguishing inapplicability from missing prerequisites.

Decision precedence:

1. An established blocking failure remains FAIL even if other checks are incomplete. Report incompleteness alongside it.
2. Unsupported scope cannot pass.
3. Missing mandatory evidence, missing pages, unavailable mandatory checks, or incomplete required matching produces INCOMPLETE.
4. Conflicting extraction, ambiguous links, or unresolved blocking review produces NEEDS_REVIEW.
5. PASS requires every mandatory applicable check to pass, required evidence coverage to be complete, and no unresolved blocker.

Nonblocking observations may coexist with PASS only under an explicit versioned policy. Risk score is a review-priority indicator, not a probability of correctness or a clearance rule. An accepted business exception must not rewrite a deterministic failure as a passed check.

## 4. Phase 0 — Establish regression cases and product contracts

Priority: P0. Dependencies: none.

Implementation:

1. Turn the four reproduced domain failures and evaluator omission into permanent minimal regression fixtures. Preserve current failing outcomes as evidence before correction.
2. Add a decision truth table covering missing references, partial line matches, extraction disagreement, failed mandatory checks, optional unavailable checks, and accepted exceptions.
3. Inventory catalog checks by required inputs, applicability, blocking behavior, tolerance, and supported business scope. Do not let callers suppress mandatory checks by omission.
4. Define versioned API schemas for the new status and coverage fields. Record legacy-to-new mappings and consumer migration steps.
5. Inventory all routes and background activities that read or mutate tenant data. Include upload, progress streams, result lookup, previews, exports, reconciliation, copilot, sessions, reviews, and logs.

Primary files: `contracts/`, `tests/test_correlation.py`, `tests/test_golden_set_eval.py`, `tests/test_server_v2.py`, `audit_v2/domain/models.py`, `audit-frontend/src/types/audit.ts`.

Exit gate: executable fixtures cover every confirmed flaw; decision and API contracts are committed; baseline results include unresolved cases.

## 5. Phase 1 — Remove false clearance paths

Priority: P0. Dependencies: Phase 0.

Implementation:

1. Introduce one pure decision function consumed by the API, reports, dashboard summaries, workflow outputs, and exports. Remove score-based pass logic and unqualified “fully compliant” prose.
2. Change three-way validators to return matching coverage: required lines, matched lines, unmatched lines, ambiguous lines, and monetary coverage where computable. Preserve denominator definitions; unknown values must not disappear from coverage.
3. No matched lines means NOT_RUN/INCOMPLETE at decision level, never PASS. Partial matching records verified comparisons but leaves required coverage incomplete.
4. Surface every blocking failed line with evidence, rather than stopping after one failure and obscuring remaining issues.
5. Add cross-check execution status: completed, not requested, unavailable, failed. Use supported=true/false only for completed analysis; otherwise null. Decide through policy whether this check is mandatory.
6. Preserve upload failures as per-file results. The batch denominator includes every accepted upload, including failed extraction and unsupported inputs.
7. Update UI, exports, summaries, and metrics together. Display missing evidence and next action beside the decision. Never render an unresolved case as a green pass through a legacy fallback.

Primary files: `audit_v2/server.py`, `audit_v2/domain/adjudicator.py`, `audit_v2/domain/validators/threeway.py`, `audit_v2/analytics/risk_scorer.py`, `audit_v2/pipeline/cross_check.py`, `audit_v2/reporting/`, `audit-frontend/src/`.

Acceptance tests:

- Unrelated invoice/PO/GRN descriptions produce zero verified coverage and no clearance.
- A score of 100 with missing mandatory references cannot pass.
- A score above 80 with a blocking failed check cannot pass.
- Cross-check outage is distinguishable from completed agreement.
- API, UI, PDF/report output, and saved session show the same decision and blockers.
- One extraction failure in a batch remains visible in counts and results.

Exit gate: zero false passes across the decision regression corpus.

## 6. Phase 2 — Correct transaction identity and matching

Priority: P0. Dependencies: Phase 0; integrate with Phase 1 coverage.

Implementation:

1. Model upload ID, original content hash, printed business number, document revision, supplier identity, buyer legal entity, and tenant separately.
2. Anchor PO identity on tenant + buyer entity + supplier + normalized printed PO number, with period/version scope where required by actual numbering policy. Missing identity is uncertainty, not permission to merge.
3. Separate candidate generation from match acceptance. Evaluate all candidates, reject hard conflicts, and retain reasons for accepted/rejected candidates. Multiple plausible candidates require review.
4. Stop propagating weak inferred links as authoritative anchors. Record whether a link was explicit, inferred, or human confirmed.
5. Make candidate ordering stable and test upload-order invariance. Batch order must not decide a transaction relationship.
6. Replace description-key dictionaries with explicit line identities and allocation records. Prefer PO line reference and supplier item code; use normalized descriptions only with supporting attributes.
7. Require compatible currency and units; apply only versioned, explicit unit conversions. Unknown conversion or mixed currency remains unresolved.
8. Allocate receipt quantities cumulatively across invoice lines and invoices. Handle split receipts, partial invoicing, repeated descriptions, returns, cancellations, and credit notes within supported scope.
9. Normalize net/gross/tax basis before cumulative value comparison. Do not assume PO totals are always pre-tax or silently mix invoice subtotals and gross amounts.
10. Track allocation provenance: every aggregate comparison cites all contributing invoice and receipt lines.
11. Re-evaluate both old and new affected clusters when links change. Supersede stale findings and invalidate dependent decisions.

Primary files: `audit_v2/domain/correlation.py`, `audit_v2/domain/models.py`, `audit_v2/domain/validators/threeway.py`, `audit_v2/domain/validators/reference_integrity.py`, `audit_v2/orchestration/cluster_audit.py`.

Acceptance tests:

- Identical PO numbers from different suppliers/entities/tenants never merge automatically.
- Two equally plausible POs produce an unresolved match, independent of upload order.
- Two invoices consuming the same ten received units cannot both claim ten units without an exception.
- Duplicate descriptions do not overwrite lines; partial receipts and unit conversion work explicitly.
- Late receipts, PO amendments, and corrected links update every affected decision with history preserved.
- Currency or tax-basis mismatch cannot produce a numeric comparison that passes silently.

Exit gate: identity, allocation, ambiguity, and order-invariance scenarios pass through both domain tests and the upload API.

## 7. Phase 3 — Repair duplicate detection and revision handling

Priority: P0. Dependencies: Phase 2 identity contract; Phase 6 for persistent completion.

Implementation:

1. Exact content duplicates use tenant-scoped hashes and return the existing upload/result reference without creating a second obligation.
2. Business duplicates use tenant/entity/supplier/document type/printed number, applying explicit numbering scope. Use the printed header number, not upload ID.
3. Treat changed amount/date/bank details under the same business identity as a conflicting version requiring review. Never silently overwrite the earlier version.
4. Keep near-duplicate detection separate as a suspicion, including rescans and changed formatting. A candidate is not automatically a proven duplicate.
5. Make duplicate checks work across transaction clusters and historical uploads. Re-evaluate previously affected documents when a duplicate arrives elsewhere.
6. Persist unique constraints and idempotency keys so concurrent submissions cannot bypass checks. Corrections must name the revision they supersede.

Acceptance tests: same printed number with altered amount/date is flagged; rescan is linked or reviewed; legitimate same number from another supplier is separate; retry creates no extra payable obligation; concurrent duplicates and restart preserve outcomes.

Exit gate: all three concepts—duplicate upload, duplicate obligation, and legitimate revision—are visibly distinct and durably enforced.

## 8. Phase 4 — Strengthen evidence and cross-verification

Priority: P1, required before expanded automatic clearance. Dependencies: Phases 0–2 contracts.

Implementation:

1. Store critical extracted values with page, bounding region or text span, label, table/row/column context, raw value, normalization, source engine, and version.
2. Ground money and identifiers in their semantic context. A matching number elsewhere on the page is insufficient. Record unavailable location evidence explicitly.
3. Bind quantity, rate, and total to the same line before calculating. Preserve repeated rows and page continuations rather than flattening them into sets.
4. Track source lineage: parsing a VLM transcript and asking another model to read that transcript are dependent observations. Do not count them as two independent confirmations.
5. Compare critical fields deterministically across available OCR/native-text/vision observations. Preserve disagreements and route unresolved ones to review.
6. Keep the language-model cross-check advisory. Require cited evidence identifiers for contradictions; reject unsupported references. Report truncation and partial inspection instead of implying full coverage.
7. Distinguish internal document consistency from independent transaction verification. Matching uploaded documents does not establish authenticity. For the supported product scope, plan authenticated supplier-master, PO, receipt, and ledger imports with source IDs and import timestamps; expose when only uploaded evidence is available.
8. Version model, prompt, parser, extraction configuration, and rule dependencies. Cache keys include these versions and input hashes.
9. Add reviewer corrections as new evidence versions. Recompute dependent checks; retain original extraction and decisions.

Primary files: `audit_v2/extraction/grounding.py`, extraction schemas/parsers/merge code, `audit_v2/pipeline/evidence_pipeline.py`, `audit_v2/pipeline/cross_check.py`, `audit_v2/domain/evidence.py`, provenance storage.

Acceptance tests: swapped subtotal/total fails semantic grounding; same number in another row cannot corroborate a field; omitted/repeated table rows remain detectable; OCR disagreement cannot be averaged into a pass; truncated model input is disclosed; a correction causes reproducible dependent re-evaluation.

Exit gate: every mandatory decision input has inspectable contextual support or a blocking reason why it does not.

## 9. Phase 5 — Enforce identity, tenancy, and review governance

Priority: P0 before any shared customer deployment. Dependencies: Phase 0 route inventory; integrate with Phase 6 persistence.

Implementation:

1. Resolve authenticated identity and permitted tenant membership on the server. Treat tenant parameters as requested scope to authorize, never identity proof.
2. Enforce access controls on every route and activity, including streaming, previews, report downloads, reconciliation, and copilot context.
3. Scope every document lookup, cache key, cluster, review, job, and uniqueness constraint by tenant. Add database-level tenant enforcement as defense in depth.
4. Wire the existing permission matrix into request handlers and service methods. Reviewer identity comes from authentication, not request JSON.
5. Enforce separation of duties for rule changes and approvals. Version rule configuration with actor identity and effective dates.
6. Make review transitions explicit, authorized, append-only, and concurrency checked. Annotation must not close a case; escalation remains actionable; conflicting simultaneous reviews cannot silently overwrite each other.
7. Separate correcting evidence, rejecting a suspected finding, confirming a failure, and accepting a business exception. Preserve deterministic results; corrections trigger a new run.
8. Configure allowed origins, upload limits, content validation, request limits, secret handling, and safe error responses for deployment. Log authorized actions without leaking document contents or secrets into diagnostics.

Acceptance tests: a tenant-A identity cannot read, stream, export, review, or correlate tenant-B data even with known IDs; forged reviewer IDs are ignored/rejected; viewers cannot approve; rule authors cannot self-approve where prohibited; concurrent review conflicts are surfaced.

Exit gate: complete API-level negative authorization suite passes with real storage and production authentication configuration.

## 10. Phase 6 — Make the actual product path durable

Priority: P0 before customer dependence. Dependencies: identity and decision contracts.

Architecture choice: Postgres is the authoritative operational store; immutable original files live in object storage; Temporal drives durable audit jobs. Reuse existing components after verifying their behavior. SQLite traces may remain a local diagnostic/export facility, but cannot be a second source of active truth.

Implementation:

1. Reconcile domain and persistence schemas before wiring stores. In particular, explicitly map finding status/expected/actual/delta fields to stored verdict/value/discrepancy columns; validate round-trip fidelity rather than assuming similarly named fields match.
2. Persist documents/revisions, extractions, evidence, candidate links, confirmed links, allocations, audit runs, findings, supersession, reviews, policies, and job events.
3. Define transaction boundaries for decisions and their supporting evidence. Store a transactional outbox for committed events, then deliver progress notifications reliably.
4. Route the real upload API through durable jobs and the same evidence pipeline used in production. Avoid maintaining a demo pipeline and a divergent durable pipeline.
5. Use stable operation IDs and uniqueness constraints for retry safety. Retrying an activity must not duplicate findings, reviews, allocations, or audit events.
6. Persist rule/model/parser versions, effective audit date, input hashes, linked document revisions, and normalized decision inputs for replay. Reproduction means replaying saved evidence deterministically; fresh model inference is a new run.
7. Recover in-flight jobs and review queues after restart. Provide a supported retry/cancel path and explicit terminal failure status.
8. Migrate existing session history with source lineage. Import legacy decisions as historical/unverified records; do not silently certify or reconstruct missing operational evidence.
9. Establish backups, restore drills, retention policy, and tamper-evident audit history. Hash chains alone do not prevent privileged rewrite; use restricted append rights and independently retained checkpoints where required.

Primary files: `audit_v2/server.py`, `audit_v2/persistence/`, `audit_v2/ingestion/document_store.py`, `audit_v2/orchestration/`, infrastructure configuration.

Acceptance tests: kill worker/API during upload, extraction, persistence, and review; restart and resume without duplicated obligations or missing history. Verify findings survive round-trip with all financial values unchanged. Restore a backup and reproduce selected decisions and evidence links. Disconnect streaming without stopping the durable audit.

Exit gate: actual upload-to-review workflow survives restart and backup recovery; no active business state depends on module-level dictionaries.

## 11. Phase 7 — Rebuild the reliability benchmark

Priority: begin immediately; release gate after fixes.

Implementation:

1. Score against the complete expected-check universe. Expected failures with no verdict, NOT_RUN, ERROR, or review must be counted as unresolved/missed automatic detections, not disappear. Preserve conditional precision/recall over completed verdicts as a separately named metric.
2. Include ingestion/extraction failures and missing documents in end-to-end denominators. Count line multiplicity rather than deduplicating repeated rows into sets.
3. Report false clearance rate among automatic passes and the rate at which defective cases are automatically passed; also report defect recall, false alarms, abstention/review rate, coverage, and reviewer correction/time metrics.
4. Remove misleading calibration claims until real confidence scores and outcomes are available. Separate classification confidence, extraction confidence, match confidence, and audit outcome. Fixed heuristic intervals must not appear as measured statistical uncertainty.
5. Add related multi-document bundles, late arrivals, duplicate revisions, repeated items, partial deliveries, currency/unit mismatches, missing pages, low-quality scans, unseen layouts, and supported language variants.
6. Obtain permissioned, de-identified real documents and independent reviewer labels with adjudication of disagreements. Split by supplier/layout/transaction family to prevent near-duplicate leakage.
7. Maintain development, locked validation, and untouched release sets. Promote reviewer feedback into development fixtures first; do not tune against the locked release set.
8. Run deterministic CI tests on every change; durable integration tests in CI with required services; scheduled live extraction evaluation with pinned versions. Store artifacts and diff metrics by model/parser/rule change.
9. Add the benchmark and frontend build/critical end-to-end tests to release gates. Code coverage alone cannot establish audit reliability.

Proposed release targets, to be finalized using representative pilot data:

- Zero false passes in the known-defect regression corpus and all mandatory invariant tests.
- Zero tenant-boundary failures and lost/duplicated obligations in recovery tests.
- Every released verdict includes scope, evidence, applicable-check coverage, and version information.
- Real-document automatic-clearance false-pass rate has a one-sided 95% upper confidence bound below the agreed risk budget. As an example, zero failures in about 600 representative independent cleared cases supports an upper bound near 0.5%; correlated layouts reduce effective sample size. This is a target design, not an existing reliability claim.
- Publish recall and unresolved rates by supported document/layout group. Do not satisfy safety targets simply by sending everything to review; agree a minimum useful automation rate and maximum reviewer workload during the pilot.
- Set measured p95 latency, throughput, queue age, and recovery objectives against declared hardware and batch sizes before release.

Primary files: `evaluation/measure_v2.py`, `evaluation/metrics.py`, golden fixtures/manifests, `tests/`, `.github/workflows/ci.yml`, frontend tests.

Exit gate: release report uses the full product path, includes uncertainty and unresolved cases, and meets predeclared thresholds on an untouched dataset.

## 12. Phase 8 — Controlled pilot and operational release

Dependencies: Phases 1–7 acceptance gates.

1. Run historical transaction bundles in shadow mode alongside reviewers; do not change financial workflow decisions automatically.
2. Triage every disagreement into extraction, matching, rule, evidence, review, or source-data cause. Add regression fixtures without contaminating the release holdout.
3. Enable assisted production for the declared scope. Provide exception ownership, missing-document requests, review aging, searchable evidence, and exportable decision history.
4. Enable automatic clearance only for supported, measured cohorts meeting the decision contract. Keep payment execution outside this release scope.
5. Monitor false-pass incidents, review reversals, missing evidence, matching ambiguity, extraction drift, job failures, and queue delay by version and cohort.
6. Provide a feature flag that disables automatic clearance while allowing ingestion and review to continue. A rollback must preserve durable state and prior decision history.
7. Publish a support/runbook covering outages, failed jobs, corrections, incidents, backups, and model/rule rollback. Assign named release and incident owners before deployment.

Exit gate: pilot metrics meet the agreed thresholds, reviewers can complete exceptions end to end, recovery is demonstrated, and automatic clearance can be disabled safely.

## 13. Suggested implementation slices and dependencies

Each slice should be independently reviewable and include its regression tests, schema migration where needed, and API/UI compatibility work.

| Slice | Deliverable | Depends on |
|---|---|---|
| 01 | Failure fixtures, decision truth table, API schemas | None |
| 02 | Authoritative decision function and truthful UI/report states | 01 |
| 03 | Matching coverage and cross-check execution states | 01–02 |
| 04 | Tenant/entity/supplier business identities and candidate ambiguity | 01 |
| 05 | Line allocations, cumulative receipt checks, tax/unit basis | 03–04 |
| 06 | Business duplicates, revision policy, affected-document reevaluation | 04–05 |
| 07 | Contextual grounding and evidence lineage | 01, 03 |
| 08 | Authentication, route authorization, review transitions | 01, 04 |
| 09 | Operational schema, adapters, migrations, round-trip tests | 02, 04, 08 contracts |
| 10 | Durable upload workflow, outbox, retry/recovery | 05–09 |
| 11 | Evaluator corrections and representative datasets | Start after 01; extend throughout |
| 12 | Integrated release gates, shadow pilot, rollout controls | All preceding slices |

Suggested owner roles: domain/backend engineer for decisions and matching; platform/backend engineer for persistence and identity; frontend engineer for evidence/review flows; QA/evaluation engineer and an experienced audit reviewer for fixtures and acceptance labels. These are work assignments to make later, not tasks already delegated.

## 14. Completion checklist

- [ ] PASS cannot be produced by score, missing comparisons, or unavailable mandatory checks.
- [ ] Every required line is matched, explicitly unresolved, or demonstrably out of scope.
- [ ] Matching is tenant/entity/supplier safe and independent of upload order.
- [ ] Quantities and values are conserved across allocations and revisions.
- [ ] Duplicate business numbers and altered versions are detected across sessions.
- [ ] Critical extracted values have contextual evidence and source lineage.
- [ ] Every endpoint and job enforces tenant and actor permissions.
- [ ] Review corrections and exceptions preserve immutable historical decisions.
- [ ] Operational state survives restart, retries, concurrency, and restore.
- [ ] Benchmark accounts for every expected case, including abstentions and errors.
- [ ] Real-document holdout results meet declared safety and usefulness gates.
- [ ] UI and exports accurately describe verified scope and unresolved work.
- [ ] Pilot monitoring, rollback, and support ownership are operational.

Do not declare completion from unit-test count, synthetic F1, feature presence, or an attractive dashboard. Completion requires the full product workflow to satisfy these gates with representative evidence.
