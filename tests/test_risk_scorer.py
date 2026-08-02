from audit_v2.analytics.risk_scorer import (
    compute_document_score,
    risk_explanation_for,
    risk_level_for,
)
from audit_v2.domain.models import Finding, FindingStatus, Severity


def _f(sev: Severity) -> Finding:
    return Finding(
        finding_id="f1",
        check_id="CHK-ARITH-LINE-001",
        document_id="doc_1",
        tenant_id="t",
        status=FindingStatus.FAIL,
        severity=sev,
        message="bad",
        decision_fingerprint="fp",
        ruleset_version="v2.0",
    )


def test_score_starts_at_100_and_subtracts_severity_weights():
    assert compute_document_score([]) == 100.0
    assert compute_document_score([_f(Severity.CRITICAL)]) == 60.0
    assert compute_document_score([_f(Severity.HIGH), _f(Severity.LOW)]) == 70.0
    assert compute_document_score([_f(Severity.CRITICAL), _f(Severity.HIGH),
                                   _f(Severity.MEDIUM), _f(Severity.LOW)]) == 20.0


def test_score_never_goes_below_zero():
    findings = [_f(Severity.CRITICAL)] * 5
    assert compute_document_score(findings) == 0.0


def test_risk_level_rules():
    assert risk_level_for(90.0, []) == "Low Risk"
    assert risk_level_for(90.0, [_f(Severity.HIGH)]) == "Medium Risk"
    assert risk_level_for(90.0, [_f(Severity.CRITICAL)]) == "High Risk"
    assert risk_level_for(75.0, []) == "Medium Risk"
    assert risk_level_for(60.0, []) == "High Risk"


def test_risk_explanation_mentions_counts():
    text = risk_explanation_for(60.0, [_f(Severity.CRITICAL), _f(Severity.LOW)])
    assert "1 critical" in text and "1 low" in text
    assert risk_explanation_for(100.0, []) != ""
