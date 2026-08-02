"""KPI + chart-data aggregation over enriched document dicts (ported from V1 aggregator)."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

RISK_COLORS = {"Low Risk": "#0F6E56", "Medium Risk": "#D97706", "High Risk": "#993C1D"}


def compute_prediction_interval(scores: list[float]) -> dict[str, float]:
    """95% confidence interval on the mean score (V1: 1.96*sigma/sqrt(n))."""
    n = len(scores)
    if n == 0:
        return {"lower": 100.0, "upper": 100.0}
    if n == 1:
        return {"lower": max(0.0, scores[0] - 12.5), "upper": min(100.0, scores[0] + 12.5)}
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / (n - 1)
    margin = 1.96 * math.sqrt(variance) / math.sqrt(n)
    return {
        "lower": round(max(0.0, mean - margin), 2),
        "upper": round(min(100.0, mean + margin), 2),
    }


def aggregate_results(documents: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(documents)
    passed = sum(1 for d in documents if d.get("passed"))
    avg = sum(d.get("score", 0.0) for d in documents) / total if total else 0.0
    violations = sum(len(d.get("failed_rules", [])) for d in documents)
    high_risk = sum(1 for d in documents if d.get("risk_level") == "High Risk")

    risk_counts = Counter(d.get("risk_level", "Low Risk") for d in documents)
    risk_distribution = [
        {"name": name, "value": count, "color": RISK_COLORS.get(name, "#6B7280")}
        for name, count in risk_counts.items()
    ]

    freq: dict[str, dict[str, Any]] = {}
    for d in documents:
        for r in d.get("failed_rules", []):
            entry = freq.setdefault(
                r["rule_id"],
                {"rule_id": r["rule_id"], "title": r.get("rule_title", r["rule_id"]), "count": 0},
            )
            entry["count"] += 1
    violation_frequency = sorted(freq.values(), key=lambda e: e["count"], reverse=True)

    compliance_trends = [
        {"name": d.get("document_name", "?"), "score": d.get("score", 0.0)} for d in documents
    ]

    type_counts = Counter(d.get("document_type", "unknown") for d in documents)
    document_types = [
        {"name": t.replace("_", " ").title(), "value": c} for t, c in type_counts.items()
    ]

    return {
        "kpis": {
            "total_audited": total,
            "compliance_rate": round(passed / total * 100, 1) if total else 0.0,
            "average_score": round(avg, 1),
            "violations_detected": violations,
            "high_risk_count": high_risk,
        },
        "charts": {
            "risk_distribution": risk_distribution,
            "violation_frequency": violation_frequency,
            "compliance_trends": compliance_trends,
            "document_types": document_types,
        },
    }
