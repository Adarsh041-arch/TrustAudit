from audit_v2.analytics.risk_predictor import predict_risk, severity_counts
from audit_v2.domain.models import Finding, FindingStatus, Severity


def _f(sev: Severity) -> Finding:
    return Finding(finding_id="f1", check_id="CHK-ARITH-LINE-001", document_id="d",
                   tenant_id="t", status=FindingStatus.FAIL, severity=sev,
                   message="bad", decision_fingerprint="fp", ruleset_version="v2.0")


def test_severity_counts_keys():
    counts = severity_counts([_f(Severity.CRITICAL), _f(Severity.HIGH), _f(Severity.MEDIUM), _f(Severity.LOW)])
    assert counts == {"critical": 1, "high": 1, "medium": 1, "low": 1}


def test_predict_compliant_when_clean():
    out = predict_risk(92.0, {"critical": 0, "high": 0, "medium": 0, "low": 0})
    assert out["prediction"] == "Compliant"
    assert out["probabilities"] == {"compliant": 90.0, "partially_compliant": 8.0, "non_compliant": 2.0}
    assert out["mode"] == "Rule-based (V2)"


def test_predict_partial_when_mid_score():
    out = predict_risk(60.0, {"critical": 0, "high": 0, "medium": 1, "low": 0})
    assert out["prediction"] == "Partially Compliant"
    assert out["probabilities"] == {"compliant": 15.0, "partially_compliant": 70.0, "non_compliant": 15.0}


def test_predict_non_compliant_when_low_score_or_critical():
    out = predict_risk(40.0, {"critical": 0, "high": 0, "medium": 0, "low": 0})
    assert out["prediction"] == "Non-Compliant"
    out2 = predict_risk(90.0, {"critical": 1, "high": 0, "medium": 0, "low": 0})
    assert out2["prediction"] == "Non-Compliant"


def test_features_used_shape():
    out = predict_risk(90.0, {"critical": 0, "high": 0, "medium": 0, "low": 0})
    assert len(out["features_used"]) == 4
