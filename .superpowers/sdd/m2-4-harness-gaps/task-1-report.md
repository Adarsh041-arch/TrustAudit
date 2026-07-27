# Task 1 Report: Expose ExtractedDocument from AuditWorkflowOutput

## Commit SHA
```
cde6d119d0f610d5fa580b9fb524dd1c88c25810
```

## Test command and result
```
pytest tests/ -x --ignore=tests/test_nvidia.py --ignore=tests/test_litert.py --ignore=tests/chaos
```
315 passed, 1 error (test_postgres_store.py — missing Postgres DSN, infra dependency, not a code issue).  
13 postgres tests skipped due to missing `AUDIT_PG_DSN` env var. 315 + 13 = 328, matching expected.

## Changes made
- `audit_v2/orchestration/workflows.py`:
  - Added `ExtractedDocument` to the import from `audit_v2.domain.models`
  - Added `document: ExtractedDocument | None = None` field to `AuditWorkflowOutput` dataclass
  - Passed `document=normalized` on the main success return path in `AuditWorkflow.run()`

## Concerns
None.