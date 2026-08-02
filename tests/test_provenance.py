"""Unit tests for ProvenanceGraph (PHASES_V2 §4 Phase 9)."""

from audit_v2.domain.models import EvidenceItem, Finding, FindingStatus, Severity
from audit_v2.persistence.provenance import ProvenanceGraph


class TestProvenanceGraph:
    def test_record_and_retrieve_evidence_chain(self):
        graph = ProvenanceGraph()
        finding = Finding(
            finding_id="fnd_100",
            check_id="CHK-ARITH-LINE-001",
            document_id="doc_abc",
            tenant_id="t1",
            check_type="line_total",
            status=FindingStatus.FAIL,
            severity=Severity.HIGH,
            message="Line total error",
            decision_fingerprint="sha256:123",
            ruleset_version="rs_v1",
            evidence=[
                EvidenceItem(document_id="doc_abc", page=1, bbox=[10, 20, 30, 40], field="quantity", raw="5")
            ],
        )

        graph.record_finding_provenance(
            finding=finding,
            document_id="doc_abc",
            ruleset_version="rs_v1",
            prompt_version="p_v1",
            model_version="gemini-flash",
        )

        nodes = graph.get_evidence_chain("fnd_100")
        assert len(nodes) >= 3  # finding node + doc node + rule node + field node
        node_types = {n.node_type for n in nodes}
        assert "finding" in node_types
        assert "document" in node_types
        assert "rule_version" in node_types
        assert "field" in node_types
