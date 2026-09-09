"""Duplicate detection — corpus-level check (Phase 7).

Pure function over a per-tenant CorpusIndex carried on the CheckContext
(built by audit_v2.domain.correlation.build_corpus_index). When no index is
present (single-document run) it SKIPs — an unrunnable check never reports
as compliant.
"""

from audit_v2.domain.correlation import (
    business_number,
    duplicate_key,
    identity_scope,
    near_duplicate_key,
)
from audit_v2.domain.models import CheckContext, CheckResult, EvidenceItem


def check_duplicate_document(ctx: CheckContext) -> CheckResult:
    """CHK-DUP-DOC-001 — detect duplicate documents in the tenant corpus."""
    check_id = "CHK-DUP-DOC-001"
    index = ctx.corpus_index
    if index is None:
        return CheckResult.unresolved(
            check_id,
            "Corpus-level check: no corpus index on this run",
        )

    doc = ctx.document
    if not identity_scope(doc)[2] or not business_number(doc):
        return CheckResult.unresolved(
            check_id, "Supplier or printed business document number is missing"
        )
    exact = [i for i in index.by_vendor_docnum.get(duplicate_key(doc), []) if i != doc.document_id]
    if exact:
        return _fail(
            ctx, check_id, "supplier+printed_document_number (possible conflicting revision)", exact
        )
    key = near_duplicate_key(doc)
    near = [i for i in index.by_vendor_amount_date.get(key or "", []) if i != doc.document_id]
    if near:
        result = _fail(ctx, check_id, "supplier+amount+date (candidate only)", near)
        from audit_v2.domain.models import FindingStatus

        result.status = FindingStatus.NEEDS_REVIEW
        return result
    return CheckResult.passed(check_id)


def _fail(
    ctx: CheckContext, check_id: str, signature: str, duplicate_ids: list[str]
) -> CheckResult:
    doc = ctx.document
    return CheckResult.failed(
        check_id,
        expected="unique document",
        actual=f"duplicate of {', '.join(sorted(duplicate_ids))}",
        delta="N/A",
        message=(
            f"Document {doc.document_id} matches {signature} signature of "
            f"{', '.join(sorted(duplicate_ids))}"
        ),
        evidence=[
            EvidenceItem(
                document_id=doc.document_id,
                page=1,
                bbox=None,
                field="document_id",
                raw=doc.document_id,
            )
        ],
        requires_human_review=True,
    )
