"""Sequence validators — CHK-SEQ-* checks.

These are corpus-level checks requiring document sequence data. Deferred to Phase 7.
Single-document checks always pass.
"""
from audit_v2.domain.models import CheckContext, CheckResult


def check_invoice_sequence(ctx: CheckContext) -> CheckResult:
    """CHK-SEQ-INVNUM-001 — invoice numbers sequential within batch (requires corpus)."""
    return CheckResult.skipped(
        "CHK-SEQ-INVNUM-001",
        "Corpus-level check: requires document sequence data (Phase 7)",
    )


def check_po_sequence(ctx: CheckContext) -> CheckResult:
    """CHK-SEQ-PONUM-001 — PO numbers sequential within batch (requires corpus)."""
    return CheckResult.skipped(
        "CHK-SEQ-PONUM-001",
        "Corpus-level check: requires document sequence data (Phase 7)",
    )


def check_challan_sequence(ctx: CheckContext) -> CheckResult:
    """CHK-SEQ-CHALLAN-001 — challan numbers sequential within batch (requires corpus)."""
    return CheckResult.skipped(
        "CHK-SEQ-CHALLAN-001",
        "Corpus-level check: requires document sequence data (Phase 7)",
    )
