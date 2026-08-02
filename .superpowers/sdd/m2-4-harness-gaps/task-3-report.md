# Task 3 Report: Wire ECE and determinism

## Commit SHA

```
fb5e7afcc6f6e5be47e4e98ef7401cd8b457446d
```

## `measure_v2.py --limit 3` output

```
Documents scored: 3
Statuses: {'READY': 3}

Per-category metrics:
category                  prec  recall      f1    tp    fp    fn    tn
----------------------------------------------------------------------
format_completeness     0.0000  0.0000  0.0000     0     0     0     9
reference_integrity     0.0000  0.0000  0.0000     0     0     0     3
sequence                0.0000  0.0000  0.0000     0     0     0     0
temporal                0.0000  0.0000  0.0000     0     0     0     0
OVERALL                 0.0000  0.0000  0.0000

Gates:
  [FAIL] arithmetic_precision: None (target 1.0)
  [FAIL] arithmetic_recall: None (target 0.98)
  [FAIL] overall_precision: 0.0 (target 0.9)
  [FAIL] overall_recall: 0.0 (target 0.85)
  [FAIL] extraction_f1: 0.0 (target 0.95)
  [PASS] ece: 0.0 (target 0.05)
  [PASS] determinism: 1.0 (target 1.0)
  ECE: 0.0
  Determinism: 1.0

Extraction field F1: 0.0000  (TP=0, FP=3, FN=3)
```

Exit code: 1 (gates fail as expected)

## Full test suite result

```
pytest tests/ -x --ignore=test_nvidia.py --ignore=test_litert.py --ignore=tests/chaos
```

315 passed (excludes 13 postgres store tests that need `AUDIT_PG_DSN` / running Postgres). Matches expected 328 total.

## Concerns

None. ECE is 0.0 because all deterministic checks have confidence=1.0 and all are correct (only TN findings in this limited sample). Determinism is 1.0 because the second pass produces identical verdicts. Both will become more meaningful as non-deterministic checks are added.
