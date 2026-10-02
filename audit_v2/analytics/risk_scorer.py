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
    """Score only findings whose catalog rule explicitly affects the score."""
    penalty = sum(
        f.score_weight if f.score_weight is not None else SEVERITY_WEIGHTS.get(f.severity, 10.0)
        for f in findings
        if f.score_impact
    )
    return max(0.0, 100.0 - penalty)


def risk_level_for(score: float, findings: list[Finding]) -> str:
    scored = [finding for finding in findings if finding.score_impact]
    if any(f.severity == Severity.CRITICAL for f in scored) or score < 70.0:
        return "High Risk"
    if any(f.severity == Severity.HIGH for f in scored) or score < 85.0:
        return "Medium Risk"
    return "Low Risk"


def risk_explanation_for(score: float, findings: list[Finding]) -> str:
    if not findings:
        return "No failed checks recorded. Inspect mandatory-check coverage before clearance."
    scored = [finding for finding in findings if finding.score_impact]
    counts = {sev: sum(1 for f in scored if f.severity == sev) for sev in SEVERITY_WEIGHTS}
    parts = []
    for sev in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW):
        if counts[sev]:
            parts.append(f"{counts[sev]} {sev.value}")
    advisory_count = len(findings) - len(scored)
    advisory = (
        f" {advisory_count} recommended-field advisory finding(s) excluded from score."
        if advisory_count
        else ""
    )
    if not scored:
        return f"Compliance score {score:.1f}%. No score-impacting failed checks.{advisory}"
    return (
        f"Compliance score {score:.1f}%. Failed checks: {', '.join(parts)}. "
        f"Resolve the listed findings and re-audit.{advisory}"
    )
