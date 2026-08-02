# Task 3 Report: analytics/aggregator.py

**Status:** DONE_WITH_CONCERNS
**Commit:** `696b951` — `feat(analytics): KPI/chart aggregation and prediction interval`
**Tests:** 4/4 passed, `ruff check` clean

## What was done

Followed the brief's TDD steps:

1. **Step 1** — Wrote `tests/test_aggregator.py` verbatim from the brief.
2. **Step 2** — Ran `python -m pytest tests/test_aggregator.py -v` → FAIL with `ModuleNotFoundError: No module named 'audit_v2.analytics.aggregator'` (expected).
3. **Step 3** — Wrote `audit_v2/analytics/aggregator.py` from the brief's code.
4. **Step 4** — Ran tests → **1 FAILED / 3 PASSED** on the first pass (see concern 1). Fixed; then **4 PASSED**, `ruff check` clean.
5. **Step 5** — Committed only the two new files with the brief's exact message.

## Deviations from the brief (both forced)

1. **Removed the `color` key from `risk_distribution` entries** (and the now-dead `RISK_COLORS` constant).
   - The brief is internally inconsistent: its test asserts membership of `{"name": "Low Risk", "value": 1}` (no `color` key) in `charts["risk_distribution"]`, but its implementation adds `color`, so the dict-equality `in` check fails. The same contradiction exists in the parent plan (`docs/superpowers/plans/2026-08-02-v1-parity.md`, test at line 301 vs implementation at line 353).
   - Resolution chosen: test is the contract → implementation drops `color`. Verified safe downstream: Task 9's frontend already falls back with `color: RISK_COLORS[name] ?? '#6B7280'`, and Task 6's brief only asserts the empty-docs shape.
   - Alternative (rejected): keeping `color` and editing the test would have violated the dispatcher's instruction that the test file be exactly as the brief specifies.
   - Note: V1's legacy aggregator (`analytics/aggregator.py:46`) does include `color`, so this is a minor V1-parity divergence; the frontend supplies colors at render time instead.
2. **Reformatted 4 lines that exceeded the repo's 100-char ruff limit** (E501). The brief's code had lines of 101/132/112/104 chars; the dispatcher required `ruff check` clean.

## Verification

```
python -m pytest tests/test_aggregator.py -v   → 4 passed in 0.75s
ruff check audit_v2/analytics/aggregator.py    → All checks passed!
git show --stat 696b951                        → 2 files changed, 116 insertions(+)
```

## Concerns

- **Plan-level bug:** the V1-parity plan/brief has a test-vs-implementation contradiction around the `color` key. If backend-supplied risk colors are desired, the plan should be amended (change the test to include `color`) and this module revisited. Otherwise the frontend fallback covers it.
- **tracker.md / shortcomings.md:** AGENTS.md instructs updating these after codebase changes, but the dispatcher scoped this commit to the two new files, and both files are already modified by parallel tasks — left untouched to avoid conflicts.

## Fix round (controller ruling)

Controller ruled the brief's TEST was the bug, not the implementation: the approved design doc and V1's legacy aggregator both specify isk_distribution entries as {name, value, color}. Restored the color key (via RISK_COLORS) in udit_v2/analytics/aggregator.py and updated 	est_charts_shapes in 	ests/test_aggregator.py to expect {name, value, color}. Re-verified: 4/4 tests pass, ruff clean. Commit 	est(analytics): expect color key in risk distribution chart data.
