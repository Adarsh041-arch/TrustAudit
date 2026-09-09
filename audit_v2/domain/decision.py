"""Authoritative clearance policy. Scores never authorize an audit pass."""

from enum import StrEnum

from pydantic import BaseModel, Field

from audit_v2.domain.models import (
    CheckCatalogEntry,
    CheckDeterminism,
    CheckResult,
    ClassificationStatus,
    DocumentType,
    ExtractedDocument,
    Finding,
    FindingStatus,
)


class AuditDecisionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"


class AuditDecision(BaseModel):
    status: AuditDecisionStatus
    blockers: list[str] = Field(default_factory=list)
    required_checks: int = 0
    completed_checks: int = 0
    policy_version: str = "clearance-1"
    scope: str = "Uploaded document consistency and transaction matching; not source authenticity"

    @property
    def passed(self) -> bool:
        return self.status == AuditDecisionStatus.PASS


def decide_document(
    document: ExtractedDocument,
    results: list[CheckResult] | list[Finding],
    catalog: list[CheckCatalogEntry],
    *,
    pipeline_review: bool = False,
) -> AuditDecision:
    required = {
        c.check_id
        for c in catalog
        if c.blocking
        and document.doc_type in c.applies_to
        and c.determinism == CheckDeterminism.DETERMINISTIC
    }
    by_id = {r.check_id: r for r in results}
    failed = [
        r.message
        for r in results
        if r.status == FindingStatus.FAIL
        and (r.check_id in required or r.check_id not in {c.check_id for c in catalog})
    ]
    missing = [
        f"{check}: mandatory check has no completed verdict"
        for check in sorted(required)
        if check not in by_id
        or by_id[check].status
        in {FindingStatus.SKIPPED, FindingStatus.NOT_RUN, FindingStatus.ERROR}
    ]
    if not document.coverage.coverage_complete:
        missing.append("Not all document pages were examined")
    review = [r.message for r in results if r.status == FindingStatus.NEEDS_REVIEW]
    review.extend(document.review_reasons)
    if pipeline_review or document.extraction_disagreements or document.grounding_rejections:
        review.append("Extraction or evidence requires review")
    if document.classification_status != ClassificationStatus.CONFIRMED:
        review.append("Document classification is not confirmed")
    unsupported = document.doc_type in {
        DocumentType.UNKNOWN,
        DocumentType.CONTRACT,
        DocumentType.LETTER,
    }
    if failed:
        status = AuditDecisionStatus.FAIL
    elif unsupported or not required:
        status = AuditDecisionStatus.UNSUPPORTED
    elif missing:
        status = AuditDecisionStatus.INCOMPLETE
    elif review:
        status = AuditDecisionStatus.NEEDS_REVIEW
    else:
        status = AuditDecisionStatus.PASS
    return AuditDecision(
        status=status,
        blockers=list(dict.fromkeys(failed + missing + review)),
        required_checks=len(required),
        completed_checks=sum(
            1
            for c in required
            if c in by_id
            and by_id[c].status
            in {FindingStatus.PASS, FindingStatus.FAIL, FindingStatus.NOT_APPLICABLE}
        ),
    )
