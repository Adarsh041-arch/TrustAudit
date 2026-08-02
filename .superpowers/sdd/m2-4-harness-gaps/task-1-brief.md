# Task 1: Expose ExtractedDocument from AuditWorkflowOutput

**Context:** The evaluation harness (`evaluation/measure_v2.py`) runs documents through `AuditWorkflow` but discards the extracted document — it only reports status and findings. Task 2 needs the `ExtractedDocument` to compare extraction quality against golden manifests.

**Goal:** Add an optional `document` field to `AuditWorkflowOutput` and populate it on the success path in `audit_v2/orchestration/workflows.py`.

**Files:**
- Modify: `audit_v2/orchestration/workflows.py`

**Requirements:**

1. Add to `AuditWorkflowOutput` dataclass:
   ```python
   document: ExtractedDocument | None = None
   ```

2. In `AuditWorkflow.run()`, find the normalized document variable (it's called `normalized` after `normalize_document(extraction.document)`) and include it in the returned `AuditWorkflowOutput` on the success path. Add:
   ```python
   document=normalized,
   ```

3. The import `from audit_v2.domain.models import ExtractedDocument` should already exist in the file. Check.

4. **Do not change:** The Temporal workflow (`temporal_workflow.py`) also has an `AuditWorkflowOutput` — leave it unchanged. Only the plain workflow output needs this.

**Test:** No new tests needed. Run:
```
pytest tests/ -x --ignore=test_nvidia.py --ignore=test_litert.py --ignore=tests/chaos
```
Expected: 328 passed.

**Report file:** `.superpowers/sdd/m2-4-harness-gaps/task-1-report.md`
Write a report to that path containing: (1) the commit SHA, (2) the test command and result, (3) any concerns.
