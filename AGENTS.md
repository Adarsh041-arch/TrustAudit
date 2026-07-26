# AGENTS.md — TrustAudit / Audit V2

## Two systems coexist

| System | Dir | Status | Port | Stack |
|--------|-----|--------|------|-------|
| **V1 (TrustAudit)** | `app/` + `backend/` + `audit-frontend/` | **FROZEN** — bugfixes only | `:8000` | LangGraph, Gemini, FastAPI, React/Vite |
| **V2 (Audit V2)** | `audit_v2/` + `contracts/` + `evaluation/` | Active development | `:8100` | Temporal, Postgres, MinIO, pure Python validators |

**Cardinal rule — no cross-imports.** Enforced by CI (`import-linter` job) and `make import-lint`:
- `audit_v2/` must not import from `app/` or `backend/`
- V1 must not import from `audit_v2/`

## V2 architecture (PHASES_V2.md)

- **Domain layer is pure** — no network calls, no model calls. Validators are plain Python functions with `Decimal` arithmetic. Makes them unit-testable with zero infra.
- **All monetary values:** `Decimal` in code, integer minor units in DB, strings in JSON. Never `float`.
- **Workflow engine:** Temporal (not LangGraph). Provides durable execution, replay, restart safety.
- **Dev stack:** Postgres 16 + MinIO + Temporal via `docker-compose up -d`.

## Key commands (V2)

```powershell
# Install V2 with dev deps
pip install -e audit_v2[dev]

# Run tests (31 tests, all pass)
pytest --cov=audit_v2 --cov-report=term-missing -v

# Lint & typecheck
ruff check audit_v2/
mypy --strict audit_v2/domain/

# Validate JSON schemas + check catalog
make validate-schemas

# Check import boundaries
make import-lint

# Full check (install → validate → lint → typecheck → import-lint → test)
make all
```

## V1 commands (legacy)

```powershell
# CLI audit on sample_docs/
python main.py

# API server
uvicorn backend.server:app --reload --port 8000

# Frontend (separate terminal)
cd audit-frontend && npm run dev
```

## Project entrypoints

- **V1 CLI:** `main.py` — builds LangGraph, invokes on `sample_docs/`
- **V1 API:** `backend/server.py` — FastAPI on `:8000`
- **V1 agent core:** `app/graph.py` — LangGraph state machine with 5 nodes
- **V1 VLM:** `app/vlm.py` — Gemini integration (B1/B4/B5 known defects: LLM does arithmetic, silent 10-page truncation, silent dedup on duplicate keys)
- **V2 domain models:** `audit_v2/domain/models.py` — ProvenancedValue, Coverage, LineItem, Finding, CheckCatalog, etc.
- **V2 validators:** `audit_v2/domain/validators/` — 8 modules, all pure functions
- **V2 check catalog:** `contracts/check_catalog.yaml` — 29 checks (96% deterministic)
- **V2 JSON Schemas:** `contracts/schemas/` — 6 schemas (coverage, provenance, document, finding, check_catalog_entry, check_catalog)
- **V2 golden set manifests:** `evaluation/golden_set/manifests/`
- **V2 test generator:** `generate_test_bill.py` — CLI with `--doc-type`, `--defects`, emits defect manifests

## Must-know rules

- **Never silently degrade.** No model response ⇒ no finding. A document that fails audit is `FAILED`/`PENDING`, never `PASS` with score 0.
- **Coverage integrity.** If `coverage_complete == false`, document is `INCOMPLETE` regardless of score.
- **Decision fingerprints.** Every finding records `sha256(ruleset | prompt | model | extractor | document_hash)`. Same fingerprint ⇒ same verdict.
- **Check `determinism` field.** A check marked `deterministic` that calls a model fails CI.

## Testing

- `pytest` runs 31 tests across `tests/` and `audit_v2/`
- Tests use `tests/conftest.py` fixtures (sample line items, check catalog, tolerance specs, etc.)
- Test categories: domain models, arithmetic validator, check catalog validity

## Notable defects in V1 (being fixed in V2)

| ID | Issue |
|----|-------|
| B1 | Arithmetic delegated to LLM (V2: pure Python validators) |
| B3 | Money as `float` (V2: `Decimal`) |
| B4 | Silent 10-page truncation (V2: explicit `coverage_complete`) |
| B5 | Silent dedup on duplicate JSON keys (V2: parse failure → retry → quarantine) |
| B6 | No prompt-injection defense (V2: structural separation + deterministic backstop) |

Whenever you install something install in dev environment.

Whenever you update something update the tracker.md file after making any changes to the codebase.

After every codebase change, read the latest entry added to tracker.md, then update shortcomings.md to reflect any new or resolved shortcomings. This keeps the living deficiencies document in sync with actual code state.