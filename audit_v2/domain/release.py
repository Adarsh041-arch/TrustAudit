"""Operational clearance switch, separate from deterministic check outcomes."""

import os

from audit_v2.domain.decision import AuditDecision, AuditDecisionStatus


def apply_release_gate(decision: AuditDecision) -> AuditDecision:
    if decision.passed and os.getenv("V2_AUTO_CLEARANCE_ENABLED", "false").lower() != "true":
        return decision.model_copy(
            update={
                "status": AuditDecisionStatus.NEEDS_REVIEW,
                "blockers": [
                    *decision.blockers,
                    "Automatic clearance is disabled; reviewer sign-off is required",
                ],
            }
        )
    return decision
