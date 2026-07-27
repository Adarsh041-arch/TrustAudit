# AUDIT_AGENT V2 — Remaining Phases Implementation Plan (M2→M6)

## Context

V2 (branch `v2-hardening`) has milestones M0/M1 done: 29-check catalog, 4 extractors, deterministic routing, pure Decimal validators (99% branch cov), injection detection, §6 harness with synthetic 200-doc golden set, Temporal workflow (time-skipping tests). Remaining work per `tracker.md` and `PHASES_V2.md` §10: M2 hardening blockers → M3 governance → M4 correlation ⭐ → M5 adjudication/provenance/review → M6 scale + V1 sunset.

Decision made: the blocked V1 baseline runs via **NVIDIA's OpenAI-compatible API** (key → `.env` as `NVIDIA_API_KEY`, never in code) using already-installed `langchain-openai`. The user-suggested model `google/diffusiongemma-26b-a4b-it` may be text-only; V1 sends page images, so a 1-doc vision smoke test comes first with fallback to a vision-capable NVIDIA-hosted model.

---

## M2 — Hardening blockers

### M2.1 Real V1 baseline via NVIDIA (first: smallest, unblocks sunset metric)
- `app/vlm.py`: add `"nvidia"` branch to existing provider switch in `VLMClient.__init__` (~line 152): `ChatOpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API_KEY"), model=...)`; extend provider dispatch (~337) and env resolution (~371, `LLM_PROVIDER=nvidia`). Add `NVIDIA_API_KEY` to `.env`.
- `evaluation/measure_v1_baseline.py`: move stub-shim install behind `--offline` flag.
- Steps: 1-doc vision smoke test → fallback model if images rejected → full 200-doc run (`--workers 2` for rate limits, raise if tolerated) → commit `evaluation/baselines/v1.json` (annotate: synthetic corpus, NVIDIA model).
- **Gate:** measured (non-stub) V1 baseline committed; tracker P0.5 closed.

### M2.2 Postgres + RLS
- `audit_v2/persistence/schema.py`: add `findings` table (money as strings per §3.4, `decision_fingerprint`, nullable `supersedes` — saves an M4 migration) + `ENABLE ROW LEVEL SECURITY` + tenant policy (`current_setting('app.tenant_id')`) on all tables.
- New `audit_v2/persistence/db.py` (small): `connect(dsn)`, `apply_schema(conn)` (idempotent DDL, no migration framework), `tenant_session()` (`SET LOCAL app.tenant_id`).
- `audit_v2/ingestion/document_store.py`: `PostgresDocumentStore` implementing the existing 5-method `DocumentStore` ABC.
- New `audit_v2/persistence/finding_store.py`: minimal insert/list, called from `run_checks_and_emit()`.
- `tests/test_postgres_store.py`: contract tests parametrized over Memory+Postgres; §3.7 cross-tenant test enumerating tables from `information_schema` (table without RLS = build failure). Skips unless `AUDIT_PG_DSN` set.
- **Gate:** DDL executes; findings persisted; per-table cross-tenant isolation proven.
- **Risk (check FIRST):** Docker Desktop on this machine unverified — run `docker compose up postgres` before starting; if broken, stop and tell the user.

### M2.3 Chaos test vs real Temporal
- `audit_v2/orchestration/worker.py`: inject `PostgresDocumentStore` when `AUDIT_PG_DSN` set; pass source paths (not PDF bytes) through workflow history.
- New `tests/chaos/test_worker_kill.py`: Temporal via docker-compose, worker subprocess, ~50-doc batch, kill mid-batch, restart → every doc terminal, finding count matches clean run, no duplicate `(document_id, check_id, fingerprint)`. `@pytest.mark.chaos`, excluded from default CI.
- **Gate (§4 P3):** zero loss, zero duplicate audits; 3 consecutive local passes.

### M2.4 §6 harness gaps
- `evaluation/measure_v2.py` only: per-field scorer vs golden manifest field values; wire up existing `evaluation/metrics.py::compute_ece` (currently no callers) over `ProvenancedValue.confidence`; cost/doc row (0 for deterministic path).
- **Gate:** header F1 ≥0.95, line-item ≥0.92, ECE ≤0.05.

### M2.5 Golden-set composition
- `evaluation/golden_set/generator.py`: emit injection-laced PDFs (reuse 10-technique corpus) with manifests expecting `QUARANTINED_SECURITY`; degraded variants (rotated, no text layer). Real anonymized docs: blocked on user supply — record explicit waiver.
- **Gate:** injection PASS rate 0 measured through `measure_v2.py`.

---

## M3 — Governance (Phase 2; breadth already done)

1. **PII redaction** — flesh out `audit_v2/gateway/pii_redactor.py` (reuse IFSC/GSTIN regexes from `audit_v2/extraction/parser.py`); populate `pii_classes` column at ingestion; wire `redact()` into `vlm_gateway.py` (only egress point). Gate: no fixture account/IFSC in any model payload.
2. **Hash-chained audit log** — new `audit_v2/persistence/audit_log.py`: `(seq, entry JSONB, prev_hash, entry_hash)`, `append()` = sha256 chain, `verify_chain()`; `REVOKE UPDATE/DELETE` + mutation trigger. Gate: superuser tamper detected.
3. **Permission matrix + SoD** — new `audit_v2/persistence/rls.py`: role×resource×action as data + pure `is_allowed()`; SoD: `rule_configurer` lacks `finding:approve`. Gate: one test per matrix cell.
4. **Retention** — new `audit_v2/persistence/retention.py`: per-tenant policy (findings 7y, renders 90d), `run_retention()`. Gate: proven on backdated synthetic rows. Backup purge = documented, not coded.
5. **Model register + residency** — `approved_models`, `tenants.residency_region` in `schema.py`; one guard in `vlm_gateway.py`. Gate: violation raises POLICY failure.

---

## M4 — Correlation (Phase 7 ⭐)

1. **Cluster builder** — new `audit_v2/domain/correlation.py` (pure, purity contract applies): linkage priority explicit `po_reference` → (vendor, amount, date-window) → fuzzy; each link records method+confidence. `TransactionCluster` in `domain/models.py`. Fixtures: generator's existing 30 vendor clusters.
2. **Replace 6 SKIP corpus checks** — real duplicate detection in `validators/duplicate.py` as pure function over a passed-in index (built by small `domain/corpus_index.py`); new `validators/threeway.py`: qty invoiced ≤ received ≤ ordered, price within tolerance, invoice-without-receipt, cumulative invoiced ≤ PO value. Same Decimal/purity conventions, ≥95% branch cov.
3. **Golden clusters with defects** — extend generator taxonomy: over-billing, split-invoice, price-variance, qty-mismatch across cluster members; `measure_v2.py` scores correlation category. Gate: correct on ≥30 clusters incl. the three fraud cases.
4. **Deferred re-evaluation** — on new cluster member, rerun cluster checks; new findings set `supersedes`. Gate: invoice-before-PO test — superseded, never duplicated.

---

## M5 — Adjudication, provenance, review loop

1. **Real VLM gateway** — implement `vlm_gateway.extract()` (stub returns `"{}"`): NVIDIA OpenAI-compatible pattern as new code (§1 forbids importing `app.vlm`); strict JSON Schema validation, retry→quarantine on parse failure; M3 redaction/register guards already at this call site. Recorded fixtures for CI + one live smoke.
2. **Adjudicator (P8)** — new `audit_v2/domain/adjudicator.py`; deterministic findings passed as frozen models (structurally cannot be overturned). Gates: immutability test; escalation precision ≥0.70 via `measure_v2.py`.
3. **Provenance graph (P9)** — closure-table DDL (`provenance_edges`); DB constraint requiring ≥1 evidence edge per finding (zero orphans by constraint). New `persistence/provenance.py`; edges written in `run_checks_and_emit()`. Gates: orphan insert rejected; `evidence_chain()` <500ms p95.
4. **Review queue (P10)** — `review_queue` table (priority = severity×value×age, SLA, actions via M3 audit log). New `audit_v2/review/queue.py`. Rejection writes golden-set candidate manifest to `evaluation/golden_set/candidates/` in the same transaction. UI skipped until requested.

---

## M6 — Scale & V1 sunset

1. Load test script (`tests/load/`, not CI): 500 docs through Temporal+Postgres; §2 budgets (≤90 min, 40 docs/min @ 16 workers).
2. Cost/doc from real gateway token usage → gate ≤₹4.00 in `measure_v2.py`.
3. Hourly reconciliation vs Postgres (reuse `ingestion/reconciliation.py`); 10 consecutive zero-discrepancy batches.
4. **Sunset:** compare `baselines/v2.json` vs M2.1 `v1.json`; if V2 ≥ V1 on all gates → freeze V1 read-only per §1.5, record in `tracker.md`.

---

## Verification (each milestone)
- Full `pytest` green + gate table in `measure_v2.py` output; chaos/load marked and run on demand.
- Milestone exit recorded in `tracker.md`.

## Risks
- NVIDIA model vision support unknown → smoke test first, fallback model.
- Docker on this Windows machine unverified → blocks M2.2/M2.3; check first.
- Real anonymized docs: user-supplied only; §6 composition waived until then.
- NVIDIA rate limits → low workers / overnight run.
- Temporal chaos flakiness on Windows → time-boxed; time-skipping tests remain CI floor.
- NVIDIA API key was pasted into chat — recommend rotating it after setup.
