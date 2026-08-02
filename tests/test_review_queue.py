"""Unit tests for ReviewQueue & Golden Set feedback loop (PHASES_V2 §4 Phase 10)."""

from audit_v2.domain.models import Finding, FindingStatus, Severity
from audit_v2.orchestration.review_queue import ReviewAction, ReviewQueue, compute_priority_score


class TestReviewQueue:
    def test_priority_score_ordering(self):
        s_crit = compute_priority_score(Severity.CRITICAL, total_value=100000.0)
        s_low = compute_priority_score(Severity.LOW, total_value=1000.0)
        assert s_crit > s_low

    def test_enqueue_and_review_flow(self):
        queue = ReviewQueue()
        finding = Finding(
            finding_id="fnd_999",
            check_id="CHK-ARITH-LINE-001",
            document_id="doc_1",
            tenant_id="t1",
            check_type="line_total",
            status=FindingStatus.FAIL,
            severity=Severity.HIGH,
            message="Line total error",
            decision_fingerprint="fp1",
            ruleset_version="rs1",
        )

        item = queue.enqueue(finding, document_id="doc_1", tenant_id="t1")
        assert item.status == "PENDING"
        assert len(queue.pending_items) == 1

        # Reject as false positive -> triggers golden-set feedback candidate
        reviewed = queue.submit_review(
            item_id=item.item_id,
            reviewer_id="rev_user_1",
            action=ReviewAction.REJECT_FALSE_POSITIVE,
            comments="False alarm due to discount column",
        )

        assert reviewed.status == "REJECTED"
        assert len(queue.pending_items) == 0
        assert len(queue.golden_set_candidates) == 1
        cand = queue.golden_set_candidates[0]
        assert cand["document_id"] == "doc_1"
        assert cand["check_id"] == "CHK-ARITH-LINE-001"
        assert "False positive rejected by reviewer rev_user_1" in cand["reason"]
