import hashlib
import json

import pytest
from fastapi.testclient import TestClient

import audit_v2.server as server
from audit_v2.analytics.risk_scorer import compute_document_score
from audit_v2.domain.models import (
    CheckCatalogEntry,
    CheckCategory,
    CheckDeterminism,
    CustomRuleDefinition,
    DocumentType,
    FindingStatus,
    ProvenancedValue,
    Severity,
    ToleranceSpec,
)
from audit_v2.domain.validation import CheckRunner
from audit_v2.pipeline.events import NullProgressSink
from tests.test_product_completion import fake_document
from tests.test_product_reliability import complete, inv


def payload(revision=0, **changes):
    return {
        "expected_revision": revision,
        "title": "Required payment terms",
        "failure_message": "Payment terms are required by our company",
        "severity": "high",
        "score_weight": 17.5,
        "blocking": True,
        "score_impact": True,
        "applies_to": ["invoice"],
        "definition": {"field_path": "header.payment_terms", "operator": "is_present"},
        **changes,
    }


def test_custom_rule_persists_executes_and_rechecks_saved_documents(monkeypatch):
    monkeypatch.setattr(server, "run_document_pipeline", fake_document)
    monkeypatch.setattr(server, "generate_preview", lambda *args: "preview")
    initial = server._process_documents(
        [("invoice.pdf", b"original", "application/pdf")],
        "tenant_default",
        NullProgressSink(),
    )
    doc_id = initial["document_results"][0]["document_id"]
    client = TestClient(server.app)
    baseline = client.get("/api/v2/rules").json()
    created = client.post("/api/v2/rules", json=payload(baseline["revision"]))
    assert created.status_code == 200, created.text
    custom = next(
        rule for rule in created.json()["rules"] if rule["source"] == "custom"
    )
    with server.OPERATIONAL_STORE.transaction("tenant_default") as tx:
        stored = tx.load()
    assert stored["rule_configuration"]["revision"] == 1
    assert stored["results"][doc_id]["rule_configuration_revision"] == 1
    finding = next(f for f in server.FINDINGS_STORE if f.check_id == custom["check_id"])
    assert finding.status == FindingStatus.FAIL and finding.score_weight == 17.5
    assert compute_document_score([finding]) == 82.5
    assert any(e["action"] == "custom_rule_created" for e in stored["log"])
    assert (
        client.put(
            f"/api/v2/rules/{custom['check_id']}",
            json={
                "expected_revision": 0,
                "enabled": False,
            },
        ).status_code
        == 409
    )
    disabled = client.put(
        f"/api/v2/rules/{custom['check_id']}",
        json={
            "expected_revision": 1,
            "enabled": False,
        },
    )
    assert disabled.status_code == 200, disabled.text
    assert not any(f.check_id == custom["check_id"] for f in server.FINDINGS_STORE)
    server.RULE_CONFIG_STORE.clear()
    assert client.get("/api/v2/rules").json()["revision"] == 2
    assert (
        client.request(
            "DELETE",
            f"/api/v2/rules/{custom['check_id']}",
            json={
                "expected_revision": 2,
            },
        ).status_code
        == 200
    )


def test_builtin_settings_apply_to_new_document_types_and_reset():
    client = TestClient(server.app)
    response = client.put(
        "/api/v2/rules/CHK-REF-BANK-001",
        json={
            "expected_revision": 0,
            "severity": "high",
            "score_weight": 11,
            "score_impact": True,
            "blocking": True,
            "applies_to": ["purchase_order"],
        },
    )
    assert response.status_code == 200, response.text
    rule = server._tenant_check_map("tenant_default")["CHK-REF-BANK-001"]
    assert rule.applies_to == [DocumentType.PURCHASE_ORDER]
    assert rule.severity == Severity.HIGH and rule.score_weight == 11
    assert (
        client.request(
            "DELETE",
            "/api/v2/rules/CHK-REF-BANK-001",
            json={
                "expected_revision": 1,
            },
        ).status_code
        == 200
    )
    reset = server._tenant_check_map("tenant_default")["CHK-REF-BANK-001"]
    assert reset.score_impact is False and reset.applies_to == [DocumentType.INVOICE]


@pytest.mark.parametrize(
    "definition",
    [
        {"field_path": "header.unknown_field", "operator": "is_present"},
        {
            "field_path": "header.grand_total",
            "operator": "greater_than",
            "expected_value": "NaN",
        },
        {
            "field_path": "header.grand_total",
            "operator": "between",
            "expected_value": "10",
            "second_value": "1",
        },
        {
            "field_path": "header.vendor_name",
            "operator": "matches_regex",
            "expected_value": "(a+)+",
        },
    ],
)
def test_invalid_custom_conditions_are_rejected(definition):
    assert (
        TestClient(server.app)
        .post("/api/v2/rules", json=payload(definition=definition))
        .status_code
        == 422
    )


def test_hosted_permissions_and_tenant_isolation(monkeypatch):
    accounts = [
        {
            "actor_id": token,
            "tenant_id": tenant,
            "role": role,
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        }
        for token, tenant, role in [
            ("configure-a", "tenant-a", "rule_configurer"),
            ("review-a", "tenant-a", "reviewer"),
            ("configure-b", "tenant-b", "admin"),
        ]
    ]
    monkeypatch.setenv("V2_AUTH_MODE", "token")
    monkeypatch.setenv("V2_AUTH_ACCOUNTS", json.dumps(accounts))
    client = TestClient(server.app)
    reviewer = {"Authorization": "Bearer review-a"}
    assert (
        client.post("/api/v2/rules", json=payload(), headers=reviewer).status_code
        == 403
    )
    response = client.post(
        "/api/v2/rules", json=payload(), headers={"Authorization": "Bearer configure-a"}
    )
    assert response.status_code == 200, response.text
    custom = next(
        rule for rule in response.json()["rules"] if rule["source"] == "custom"
    )
    other = {"Authorization": "Bearer configure-b"}
    assert not any(
        r["source"] == "custom"
        for r in client.get("/api/v2/rules", headers=other).json()["rules"]
    )
    assert (
        client.put(
            f"/api/v2/rules/{custom['check_id']}",
            json={
                "expected_revision": 0,
                "enabled": False,
            },
            headers=other,
        ).status_code
        == 404
    )


def test_numeric_custom_condition_executes_with_decimal_precision():
    doc = complete(inv(doc_id="numeric"))
    doc.header.grand_total = ProvenancedValue(value="100.00001", raw="100.00001")
    definition = CustomRuleDefinition(
        field_path="header.grand_total",
        operator="between",
        expected_value="0",
        second_value="1000000",
    )
    check = CheckCatalogEntry(
        check_id="CHK-CUSTOM-TEST-001",
        title="Allowed total",
        category=CheckCategory.THRESHOLD,
        applies_to=[DocumentType.INVOICE],
        severity=Severity.HIGH,
        determinism=CheckDeterminism.DETERMINISTIC,
        inputs=[definition.field_path],
        tolerance=ToleranceSpec(type="none"),
        failure_message="Total out of bounds",
        source="custom",
        custom_definition=definition,
    )
    results = CheckRunner([check]).run_all(doc, [check.check_id], {})
    assert results[0].status == FindingStatus.PASS
