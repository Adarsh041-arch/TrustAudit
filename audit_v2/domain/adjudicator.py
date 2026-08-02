"""Adjudicator Engine — Phase 8 (PHASES_V2 §4 Phase 8).

Merges findings, resolves extraction disagreement, evaluates model-assisted checks,
and generates reviewer-facing explanations.

Absolute Structural Invariant:
The adjudicator MAY NEVER overturn a deterministic validator's arithmetic verdict.
Deterministic FAILs remain FAILs regardless of model opinion.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from audit_v2.domain.models import (
    Finding,
    FindingStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class AdjudicationRequest:
    document_id: str
    tenant_id: str
    deterministic_findings: list[Finding]
    model_assisted_findings: list[Finding] | None = None
    extraction_disagreements: dict[str, Any] | None = None


@dataclass
class AdjudicationResult:
    document_id: str
    final_findings: list[Finding]
    requires_human_review: bool
    summary: str
    escalation_reason: str | None = None


class Adjudicator:
    """Adjudicates findings and produces human-review recommendations."""

    def adjudicate(self, req: AdjudicationRequest) -> AdjudicationResult:
        final_findings: list[Finding] = []
        requires_human_review = False
        escalations: list[str] = []

        # 1. Enforce structural immutability of deterministic verdicts
        for finding in req.deterministic_findings:
            # Deterministic FAIL/NEEDS_REVIEW findings CANNOT be converted to PASS
            final_findings.append(finding)
            if finding.status == FindingStatus.FAIL or finding.requires_human_review:
                requires_human_review = True
                if finding.status == FindingStatus.FAIL:
                    escalations.append(
                        f"Deterministic failure on check {finding.check_id}: {finding.message}"
                    )

        # 2. Process model-assisted findings
        if req.model_assisted_findings:
            for f in req.model_assisted_findings:
                final_findings.append(f)
                if f.status == FindingStatus.FAIL or f.requires_human_review:
                    requires_human_review = True
                    escalations.append(
                        f"Model-assisted check {f.check_id}: {f.message}"
                    )

        # 3. Two-vendor disagreement signal (PHASES_V2 §4 Phase 8)
        if req.extraction_disagreements:
            requires_human_review = True
            disagreed_fields = ", ".join(sorted(req.extraction_disagreements.keys()))
            escalations.append(
                f"Two-vendor extraction disagreement on fields: {disagreed_fields}"
            )

        summary = (
            f"Adjudication completed for document {req.document_id}: "
            f"{len(final_findings)} total findings. "
            f"Human review required: {requires_human_review}."
        )

        escalation_reason = "; ".join(escalations) if escalations else None

        return AdjudicationResult(
            document_id=req.document_id,
            final_findings=final_findings,
            requires_human_review=requires_human_review,
            summary=summary,
            escalation_reason=escalation_reason,
        )
