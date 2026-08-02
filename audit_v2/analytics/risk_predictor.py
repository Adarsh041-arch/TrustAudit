"""Deterministic rule-based compliance prediction (V1's ML card, no sklearn).

V1's Random Forest was trained on synthetic data and never wired into the
pipeline; the rule-based fallback V1 already shipped is the honest port.
"""
from __future__ import annotations

from audit_v2.domain.models import Finding, Severity


def severity_counts(findings: list[Finding]) -> dict[str, int]:
    return {sev.value: sum(1 for f in findings if f.severity == sev) for sev in Severity}


def predict_risk(score: float, counts: dict[str, int]) -> dict[str, object]:
    has_critical = counts.get("critical", 0) > 0
    has_high = counts.get("high", 0) > 0
    features = [score, float(counts.get("critical", 0)), float(counts.get("high", 0)),
                float(counts.get("medium", 0)) + float(counts.get("low", 0))]
    if score >= 85.0 and not has_critical and not has_high:
        return {"prediction": "Compliant",
                "probabilities": {"compliant": 90.0, "partially_compliant": 8.0,
                                  "non_compliant": 2.0},
                "features_used": features, "mode": "Rule-based (V2)"}
    if score >= 50.0 and not has_critical:
        return {"prediction": "Partially Compliant",
                "probabilities": {"compliant": 15.0, "partially_compliant": 70.0,
                                  "non_compliant": 15.0},
                "features_used": features, "mode": "Rule-based (V2)"}
    return {"prediction": "Non-Compliant",
            "probabilities": {"compliant": 2.0, "partially_compliant": 18.0, "non_compliant": 80.0},
            "features_used": features, "mode": "Rule-based (V2)"}
