from audit_v2.analytics.aggregator import aggregate_results, compute_prediction_interval


def _doc(name: str, doc_type: str, passed: bool, score: float, risk: str, rules: list[dict]) -> dict:
    return {"document_name": name, "document_type": doc_type, "passed": passed,
            "score": score, "risk_level": risk, "failed_rules": rules}


def test_kpis_empty():
    out = aggregate_results([])
    assert out["kpis"] == {"total_audited": 0, "compliance_rate": 0.0, "average_score": 0.0,
                           "violations_detected": 0, "high_risk_count": 0}
    assert out["charts"]["risk_distribution"] == []


def test_kpis_counts():
    docs = [
        _doc("a", "invoice", True, 90.0, "Low Risk", []),
        _doc("b", "invoice", False, 50.0, "High Risk", [{"rule_id": "CHK-ARITH-LINE-001", "rule_title": "t", "severity": "high"}]),
        _doc("c", "purchase_order", False, 60.0, "Medium Risk", [{"rule_id": "CHK-ARITH-LINE-001", "rule_title": "t", "severity": "high"}]),
    ]
    out = aggregate_results(docs)
    k = out["kpis"]
    assert k["total_audited"] == 3 and k["compliance_rate"] == round(1 / 3 * 100, 1)
    assert k["average_score"] == round((90 + 50 + 60) / 3, 1)
    assert k["violations_detected"] == 2 and k["high_risk_count"] == 1


def test_charts_shapes():
    docs = [
        _doc("a", "invoice", True, 90.0, "Low Risk", []),
        _doc("b", "invoice", False, 50.0, "High Risk", [{"rule_id": "CHK-ARITH-LINE-001", "rule_title": "Line total", "severity": "high"}]),
    ]
    charts = aggregate_results(docs)["charts"]
    assert {"name": "Low Risk", "value": 1, "color": "#0F6E56"} in charts["risk_distribution"]
    assert charts["violation_frequency"][0] == {"rule_id": "CHK-ARITH-LINE-001", "title": "Line total", "count": 1}
    assert charts["document_types"] == [{"name": "Invoice", "value": 2}]
    assert charts["compliance_trends"] == [{"name": "a", "score": 90.0}, {"name": "b", "score": 50.0}]


def test_prediction_interval_edge_cases():
    assert compute_prediction_interval([]) == {"lower": 100.0, "upper": 100.0}
    assert compute_prediction_interval([70.0]) == {"lower": 57.5, "upper": 82.5}
    out = compute_prediction_interval([80.0, 90.0, 100.0])
    assert 0.0 <= out["lower"] <= out["upper"] <= 100.0
