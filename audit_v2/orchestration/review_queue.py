"""Human Review Queue & Golden Set Feedback Loop — Phase 10 (PHASES_V2 §4 Phase 10).

Manages human reviewer action history, queue prioritization (severity x value x age),
and the golden-set feedback loop where rejected findings become evaluation candidates.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from audit_v2.domain.models import Finding, Severity

logger = logging.getLogger(__name__)


class ReviewAction(StrEnum):
    CONFIRM = "confirm"
    REJECT_FALSE_POSITIVE = "reject_as_false_positive"
    ESCALATE = "escalate"
    ANNOTATE = "annotate"


@dataclass
class ReviewItem:
    item_id: str
    finding: Finding
    document_id: str
    tenant_id: str
    created_at: str
    priority_score: float
    status: str = "PENDING"  # PENDING | CONFIRMED | REJECTED | ESCALATED
    reviewer_id: str | None = None
    action: ReviewAction | None = None
    comments: str | None = None


SEVERITY_WEIGHTS = {
    Severity.CRITICAL: 10.0,
    Severity.HIGH: 5.0,
    Severity.MEDIUM: 2.0,
    Severity.LOW: 1.0,
}


def compute_priority_score(
    severity: Severity, total_value: float = 0.0, age_hours: float = 0.0,
) -> float:

    base = SEVERITY_WEIGHTS.get(severity, 1.0)
    value_factor = 1.0 + (total_value / 100000.0)
    age_factor = 1.0 + (age_hours / 24.0)
    return base * value_factor * age_factor


class ReviewQueue:
    """Manages reviewer action history and golden-set candidate extraction."""

    def __init__(self) -> None:
        self._items: dict[str, ReviewItem] = {}
        self._golden_set_candidates: list[dict[str, Any]] = []

    @property
    def pending_items(self) -> list[ReviewItem]:
        items = [item for item in self._items.values() if item.status == "PENDING"]
        return sorted(items, key=lambda x: x.priority_score, reverse=True)

    @property
    def golden_set_candidates(self) -> list[dict[str, Any]]:
        return list(self._golden_set_candidates)

    def enqueue(
        self,
        finding: Finding,
        document_id: str,
        tenant_id: str,
        total_value: float = 0.0,
    ) -> ReviewItem:
        ts = datetime.now(UTC).isoformat()
        score = compute_priority_score(finding.severity, total_value=total_value)
        item = ReviewItem(
            item_id=f"rev_{finding.finding_id}",
            finding=finding,
            document_id=document_id,
            tenant_id=tenant_id,
            created_at=ts,
            priority_score=score,
        )
        self._items[item.item_id] = item
        return item

    def submit_review(
        self,
        item_id: str,
        reviewer_id: str,
        action: ReviewAction,
        comments: str | None = None,
    ) -> ReviewItem:
        item = self._items.get(item_id)
        if item is None:
            raise ValueError(f"Review item {item_id} not found")

        item.reviewer_id = reviewer_id
        item.action = action
        item.comments = comments

        if action == ReviewAction.CONFIRM:
            item.status = "CONFIRMED"
        elif action == ReviewAction.REJECT_FALSE_POSITIVE:
            item.status = "REJECTED"
            # Feedback loop (PHASES_V2 §4 Phase 10):
            # Every false positive flows back into candidate golden-set fixtures
            self._golden_set_candidates.append({
                "candidate_id": f"gold_cand_{item.finding.finding_id}",
                "document_id": item.document_id,
                "check_id": item.finding.check_id,
                "reason": f"False positive rejected by reviewer {reviewer_id}",
                "finding": item.finding.model_dump(),
                "created_at": datetime.now(UTC).isoformat(),
            })
            logger.info(
                "Finding %s rejected as false positive -> candidate golden set",
                item.finding.finding_id,
            )
        elif action == ReviewAction.ESCALATE:
            item.status = "ESCALATED"

        return item
