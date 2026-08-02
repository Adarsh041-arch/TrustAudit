"""Deterministic severity-weighted document scoring (ported from V1 risk_scorer)."""
from __future__ import annotations

from audit_v2.domain.models import Finding, Severity

SEVERITY_WEIGHTS: dict[Severity, float] = {
    Severity.CRITICAL: 40.0,
    Severity.HIGH: 25.0,
    Severity.MEDIUM: 10.0,
    Severity.LOW: 5.0,
}


def compute_document_score(findings: list[Finding]) -> float:
    """100 minus the sum of severity weights of the document's failed findings."""
    penalty = sum(SEVERITY_WEIGHTS.get(f.severity, 10.0) for f in findings)
    return max(0.0, 100.0 - penalty)


def risk_level_for(score: float, findings: list[Finding]) -> str:
    if any(f.severity == Severity.CRITICAL for f in findings) or score < 70.0:
        return "High Risk"
    if any(f.severity == Severity.HIGH for f in findings) or score < 85.0:
        return "Medium Risk"
    return "Low Risk"


def risk_explanation_for(score: float, findings: list[Finding]) -> str:
    if not findings:
        return "No failed checks. Document is fully compliant."
    counts = {
        sev: sum(1 for f in findings if f.severity == sev) for sev in SEVERITY_WEIGHTS
    }
    parts = []
    for sev in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW):
        if counts[sev]:
            parts.append(f"{counts[sev]} {sev.value}")
    return (
        f"Compliance score {score:.1f}%. Failed checks: {', '.join(parts)}. "
        "Resolve the listed findings and re-audit."
    )
