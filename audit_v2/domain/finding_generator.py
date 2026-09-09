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
    FindingStatus,
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
    payload = document.model_dump_json(exclude={
        "document_id", "tenant_id", "extraction_latency_ms", "transcript_cache_hit",
        "vision_call_count", "glm_call_count",
    })
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"



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
    context_hash: str | None = None,
) -> Finding:
    """Convert a CheckResult into a persisted Finding.

    - PASS results are emitted with no expected/actual/delta.
    - FAIL results preserve expected/actual/delta and the full evidence list.
    - The decision_fingerprint is sha256(ruleset_version|prompt_version|
      model_version|extractor_version|document_hash). Two findings with the
      same fingerprint MUST agree (PHASES_V2.md §3.6).
    - `context_hash`: for cross-document checks the verdict depends on more
      than this document — pass a hash of the cluster/corpus context so the
      fingerprint changes when the context does.
    """
    requires_review = result.status not in {FindingStatus.PASS, FindingStatus.NOT_APPLICABLE} and (
        check_entry.severity == Severity.CRITICAL
        or check_entry.requires_human_review
        or result.requires_human_review
    )

    doc_hash = _document_hash(document)
    if context_hash is not None:
        doc_hash = f"{doc_hash}+ctx:{context_hash}"

    fingerprint = make_fingerprint(
        ruleset_version=ruleset_version,
        prompt_version=prompt_version,
        model_version=model_version,
        extractor_version=document.extractor_version,
        document_hash=f"{doc_hash}|{result.check_id}|{result.model_dump_json()}",
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
        coverage=result.coverage,
        decision_fingerprint=fingerprint,
        ruleset_version=ruleset_version,
        requires_human_review=requires_review,
        created_at=datetime.now(UTC),
    )
