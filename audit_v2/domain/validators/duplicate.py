"""Duplicate detection — corpus-level check.

PHASES_V2 §4 Phase 6: duplicate detection is inherently corpus-level and
requires a per-tenant index of (vendor, document_number) and
(vendor, amount, date). It cannot be answered from a single document, so this
returns SKIPPED rather than PASS — an unimplemented check must never report
as compliant.
"""
from audit_v2.domain.models import CheckContext, CheckResult


def check_duplicate_document(ctx: CheckContext) -> CheckResult:
    """CHK-DUP-DOC-001 — detect near-duplicate documents in corpus."""
    return CheckResult.skipped(
        "CHK-DUP-DOC-001",
        "Corpus-level check: requires per-tenant duplicate index (Phase 7)",
    )
