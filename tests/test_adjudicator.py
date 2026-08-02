"""Unit tests for Adjudicator (PHASES_V2 §4 Phase 8)."""

from audit_v2.domain.adjudicator import AdjudicationRequest, Adjudicator
from audit_v2.domain.models import CheckDeterminism, Finding, FindingStatus, Severity


def make_finding(check_id: str, status: FindingStatus, determinism: CheckDeterminism) -> Finding:
    return Finding(
        finding_id=f"fnd_{check_id}",
        check_id=check_id,
        document_id="doc_1",
        tenant_id="t1",
        check_type="test",
        status=status,
        severity=Severity.HIGH,
        message=f"Finding {check_id}",
        decision_fingerprint="fp123",
        ruleset_version="rs1",
    )


class TestAdjudicator:
    def test_cannot_overturn_deterministic_verdict(self):
        adj = Adjudicator()
        f_det_fail = make_finding("CHK-ARITH-LINE-001", FindingStatus.FAIL, CheckDeterminism.DETERMINISTIC)
        f_model = make_finding("CHK-FORMAT-WORDS-001", FindingStatus.PASS, CheckDeterminism.MODEL_ASSISTED)

        req = AdjudicationRequest(
            document_id="doc_1",
            tenant_id="t1",
            deterministic_findings=[f_det_fail],
            model_assisted_findings=[f_model],
        )

        res = adj.adjudicate(req)
        assert res.requires_human_review is True
        assert len(res.final_findings) == 2
        # Deterministic FAIL is preserved
        assert res.final_findings[0].status == FindingStatus.FAIL
        assert "Deterministic failure on check CHK-ARITH-LINE-001" in res.escalation_reason

    def test_two_vendor_disagreement_triggers_escalation(self):
        adj = Adjudicator()
        f_pass = make_finding("CHK-ARITH-LINE-001", FindingStatus.PASS, CheckDeterminism.DETERMINISTIC)

        req = AdjudicationRequest(
            document_id="doc_1",
            tenant_id="t1",
            deterministic_findings=[f_pass],
            extraction_disagreements={"grand_total": ("100.00", "200.00")},
        )

        res = adj.adjudicate(req)
        assert res.requires_human_review is True
        assert "Two-vendor extraction disagreement on fields: grand_total" in res.escalation_reason
