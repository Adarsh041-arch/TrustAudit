"""Duplicate detection — corpus-level check (Phase 7).

Pure function over a per-tenant CorpusIndex carried on the CheckContext
(built by audit_v2.domain.correlation.build_corpus_index). When no index is
present (single-document run) it SKIPs — an unrunnable check never reports
as compliant.
"""
from audit_v2.domain.models import CheckContext, CheckResult, EvidenceItem


def check_duplicate_document(ctx: CheckContext) -> CheckResult:
    """CHK-DUP-DOC-001 — detect duplicate documents in the tenant corpus."""
    check_id = "CHK-DUP-DOC-001"
    index = ctx.corpus_index
    if index is None:
        return CheckResult.skipped(
            check_id, "Corpus-level check: no corpus index on this run",
        )

    doc = ctx.document
    vendor = (doc.header.vendor_name.value if doc.header.vendor_name else "").strip().casefold()
    docnum = doc.document_id.strip().casefold()

    def _others(ids: list[str]) -> list[str]:
        return [i for i in ids if i != doc.document_id]

    # Exact: same vendor + same document number appearing more than once.
    if vendor and docnum:
        dupes = _others(index.by_vendor_docnum.get(f"{vendor}||{docnum}", []))
        if dupes:
            return _fail(ctx, check_id, "vendor+document_number", dupes)

    # Near: same vendor + same amount + same date under a different number,
    # scoped to the same document type (a PO/contract/certificate sharing an
    # invoice's amount+date is a legitimate match, not a duplicate).
    if vendor and doc.header.grand_total is not None:
        date_pv = doc.header.invoice_date or doc.header.order_date
        if date_pv is not None:
            try:
                amount = doc.header.grand_total.decimal_value
            except ValueError:
                amount = None
            if amount is not None:
                key = f"{vendor}||{doc.doc_type.value}||{amount}||{date_pv.value}"
                dupes = _others(index.by_vendor_amount_date.get(key, []))
                if dupes:
                    return _fail(ctx, check_id, "vendor+amount+date", dupes)

    return CheckResult.passed(check_id)


def _fail(ctx: CheckContext, check_id: str, signature: str,
          duplicate_ids: list[str]) -> CheckResult:
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
        evidence=[EvidenceItem(
            document_id=doc.document_id,
            page=1,
            bbox=None,
            field="document_id",
            raw=doc.document_id,
        )],
        requires_human_review=True,
    )
