"""Emission layer: convert a CheckResult into a Finding with decision fingerprint.

This is the M1 thin-slice glue between deterministic validators and
the persisted audit log. It is the structural guarantee that every
audit verdict is reproducible (§3.6) and evidence-backed (§4 Phase 9).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from audit_v2.domain.models import (
    CheckCatalogEntry,
    CheckResult,
    ExtractedDocument,
    Finding,
    Severity,
    make_fingerprint,
)


def _document_hash(document: ExtractedDocument) -> str:
    """Stable content hash of the extracted document.

    Covers every field that can change an audit verdict. Deliberately excludes
    document_id and tenant_id: the hash is of content, not identity, so the same
    document ingested twice yields the same fingerprint — which is what makes
    the §8 fingerprint-keyed cache and §3.6 reproducibility claim work.
    """
    h = document.header
    parts: list[str] = [
        document.doc_type.value,
        document.extractor_version,
        f"pages:{document.coverage.pages_total}",
        f"examined:{document.coverage.pages_examined}",
        f"unreadable:{sorted(document.coverage.pages_unreadable)}",
        f"complete:{document.coverage.coverage_complete}",
    ]
    for name in (
        "vendor_name", "vendor_gstin", "buyer_name", "buyer_gstin",
        "invoice_date", "due_date", "order_date", "delivery_date",
        "expiry_date", "received_date", "grn_date", "po_reference",
        "subtotal", "discount_amount", "discount_percentage", "grand_total",
        "opening_balance", "receipts", "payments", "closing_balance",
    ):
        value = getattr(h, name, None)
        if value is not None:
            parts.append(f"{name}:{value.value}")
    if h.bank_details:
        parts.append("bank:" + ",".join(f"{k}={v}" for k, v in sorted(h.bank_details.items())))
    for li in document.line_items:
        hsn = li.hsn_sac.value if li.hsn_sac else ""
        parts.append(
            f"L{li.line_number}:{li.description.value}|{li.quantity.value}"
            f"|{li.unit_price.value}|{li.line_total.value}|{hsn}"
        )
    for tl in document.tax_lines:
        parts.append(
            f"T{tl.line_number}:{tl.description.value}|{tl.taxable_value.value}"
            f"|{tl.rate.value}|{tl.cgst.value}|{tl.sgst.value}|{tl.total_tax.value}"
        )

    raw = "|".join(parts)
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"


def _document_currency(document: ExtractedDocument) -> str | None:
    for source in (document.header.grand_total, document.header.subtotal):
        if source is not None and source.currency:
            return source.currency
    for li in document.line_items:
        if li.line_total.currency:
            return li.line_total.currency
    return None


def make_finding_from_result(
    result: CheckResult,
    check_entry: CheckCatalogEntry,
    document: ExtractedDocument,
    ruleset_version: str,
    prompt_version: str,
    model_version: str,
) -> Finding:
    """Convert a CheckResult into a persisted Finding.

    - PASS results are emitted with no expected/actual/delta.
    - FAIL results preserve expected/actual/delta and the full evidence list.
    - The decision_fingerprint is sha256(ruleset_version|prompt_version|
      model_version|extractor_version|document_hash). Two findings with the
      same fingerprint MUST agree (PHASES_V2.md §3.6).
    """
    requires_review = (
        check_entry.severity == Severity.CRITICAL
        or check_entry.requires_human_review
        or result.requires_human_review
    )

    fingerprint = make_fingerprint(
        ruleset_version=ruleset_version,
        prompt_version=prompt_version,
        model_version=model_version,
        extractor_version=document.extractor_version,
        document_hash=_document_hash(document),
    )

    finding_id = f"fnd_{uuid.uuid4().hex[:12]}"

    return Finding(
        finding_id=finding_id,
        check_id=result.check_id,
        document_id=document.document_id,
        tenant_id=document.tenant_id,
        status=result.status,
        severity=check_entry.severity,
        expected=result.expected,
        actual=result.actual,
        delta=result.delta,
        currency=_document_currency(document),
        tolerance=check_entry.tolerance.value,
        message=result.message,
        evidence=list(result.evidence),
        decision_fingerprint=fingerprint,
        ruleset_version=ruleset_version,
        requires_human_review=requires_review,
        created_at=datetime.now(UTC),
    )
