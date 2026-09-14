# Product reliability implementation status

Updated 2026-09-10.

This note records what is implemented and locally verified for the product reliability plan. It is deliberately separate from the release decision: passing local tests does not certify automatic clearance on real financial documents.

## Implemented and verified locally

- Deterministic decision gating: missing, unavailable, contradictory, unsupported, or review-required checks cannot produce an automatic pass. A score is informational only.
- Coverage-aware three-way matching with tenant/entity scoping, ambiguous candidate handling, line multiplicity, cumulative receipt allocation, unit/currency compatibility, and duplicate business-number detection.
- Contextual evidence grounding, provenance and lineage, injection scanning, contradiction capture, and explicit extraction/cross-check execution states.
- Authenticated tenant and role enforcement, reviewer version checks, reviewer self-approval prevention, correction history, retained original documents, and correction-triggered re-audit.
- Tenant-scoped operational persistence with revision history, integrity fingerprints, outbox records, Postgres RLS/advisory-lock setup, and idempotent operation receipts.
- Content-addressed tenant artifact storage with atomic local writes and optional S3 storage.
- Retained upload sources, local restart recovery, cancellation-before-commit protection, retry routes, and Temporal job tenant prefixes.
- Verified local backup/restore tooling with SQLite integrity checks, SHA-256 manifests, tamper detection, path/symlink checks, and overwrite refusal.
- V2 workspace UI with clear verified/review/failed/incomplete states, evidence-oriented tracking, recovery controls, and reviewer correction workflow.
- Evaluation harness counts missing expected documents, errors, abstentions, and repeated lines; reports false-clearance and unresolved rates by cohort; synthetic data is labelled as synthetic.

## Evidence run on this checkout

- `pytest tests --ignore=tests/chaos --ignore=tests/test_temporal_workflow.py --ignore=tests/test_postgres_store.py -q`: **600 passed, 9 skipped**.
- `pytest tests/test_product_completion.py -q`: **4 passed**.
- Ruff: all checked backend, reconciliation, evaluation, and test modules pass.
- Mypy: **100 audit_v2 source files pass**.
- Frontend TypeScript build and Vite production build pass.
- Import-linter: **3 contracts kept, 0 broken**.

The skipped tests require external Postgres, Temporal, or chaos infrastructure; they are not evidence that those services are configured here.

## Remaining release gates

1. Run the workflow against a permissioned, de-identified, independently labelled real-document holdout split by supplier/layout/transaction family. Publish false-clearance upper bounds, recall, abstention, coverage, latency, and reviewer workload by cohort.
2. Deploy and exercise Postgres RLS, the durable job service, shared artifact storage, outbox publishing, and worker/API restart drills. Confirm the deployed session/progress ledger is shared by API and workers rather than local to one host.
3. Define retention, deletion, encryption/key rotation, backup cadence, restore ownership, incident response, and named release/reviewer owners. Pause writes for a consistent multi-store backup and perform a scheduled restore drill.
4. Complete a shadow pilot, then enable automatic clearance only for measured supported cohorts. Keep `V2_AUTO_CLEARANCE_ENABLED=false` until the release gate is approved; retain rollback and prior decision history.

Until these gates are completed, the product is suitable for controlled testing and assisted review, not an unattended financial clearance service.
