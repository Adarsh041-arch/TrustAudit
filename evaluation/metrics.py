#!/usr/bin/env python3
"""Evaluation metrics for the audit system.

Provides computation of precision, recall, F1, ECE (expected calibration error),
and determinism (repeat-run agreement) per check category.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class ConfusionMatrix:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        denom = p + r
        return 2 * p * r / denom if denom > 0 else 0.0


@dataclass
class CategoryMetrics:
    category: str
    matrix: ConfusionMatrix = field(default_factory=ConfusionMatrix)
    total_documents: int = 0
    total_findings: int = 0


def compute_ece(confidences: Sequence[float], correct: Sequence[bool], n_bins: int = 10) -> float:
    """Expected Calibration Error.

    Bins predictions by confidence and measures the gap between
    mean confidence and observed accuracy in each bin.
    """
    if not confidences:
        return 0.0

    pairs = list(zip(confidences, correct))
    pairs.sort(key=lambda x: x[0])

    bin_size = len(pairs) // n_bins or 1
    total_error = 0.0

    for i in range(0, len(pairs), bin_size):
        batch = pairs[i : i + bin_size]
        if not batch:
            continue
        avg_conf = sum(c for c, _ in batch) / len(batch)
        acc = sum(1 for _, corr in batch if corr) / len(batch)
        total_error += abs(avg_conf - acc) * (len(batch) / len(pairs))

    return total_error


def determinism_score(run1_verdicts: dict[str, bool], run2_verdicts: dict[str, bool]) -> float:
    """Fraction of findings where PASS/FAIL agrees between two runs.

    Keys are finding IDs, values are True for PASS, False for FAIL.
    """
    common = set(run1_verdicts) | set(run2_verdicts)
    if not common:
        return 0.0
    agreements = sum(1 for k in common if k in run1_verdicts and k in run2_verdicts
                     and run1_verdicts[k] == run2_verdicts[k])
    return agreements / len(common)


def aggregate_metrics(category_matrices: dict[str, ConfusionMatrix]) -> dict:
    """Roll up per-category metrics into an overall report."""
    total = ConfusionMatrix()
    per_category = {}

    for cat, m in category_matrices.items():
        total.tp += m.tp
        total.fp += m.fp
        total.fn += m.fn
        total.tn += m.tn
        per_category[cat] = {
            "precision": round(m.precision, 4),
            "recall": round(m.recall, 4),
            "f1": round(m.f1, 4),
            "tp": m.tp,
            "fp": m.fp,
            "fn": m.fn,
            "tn": m.tn,
        }

    return {
        "overall": {
            "precision": round(total.precision, 4),
            "recall": round(total.recall, 4),
            "f1": round(total.f1, 4),
        },
        "per_category": per_category,
    }
