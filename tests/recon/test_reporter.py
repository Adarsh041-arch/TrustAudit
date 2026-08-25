"""Reporter tests: bytes out, correct magic, exception rows present."""
from __future__ import annotations

import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO

from reconcile.models import (
    ExceptionType,
    LedgerRecord,
    MatchResult,
    MatchStatus,
    PayoutRecord,
    ReconciliationRun,
)
from reconcile.reporter import generate_docx_recon_report, generate_pdf_recon_report


def run() -> ReconciliationRun:
    exc = MatchResult(
        txn_id="TXN1042", status=MatchStatus.EXCEPTION,
        payout=PayoutRecord(txn_id="TXN1042", payout_amount=Decimal("1000.00"),
                            payout_date=date(2026, 7, 5), settlement_status="ok"),
        bank=None,
        ledger=LedgerRecord(invoice_id="TXN1042", expected_amount=Decimal("1000.00"),
                            due_date=date(2026, 8, 4), payer_id="P1"),
        exception_type=ExceptionType.MISSING_BANK_CREDIT,
        decision_fingerprint="sha256:abc",
        llm_explanation="Settlement pending with the bank.",
    )
    return ReconciliationRun(
        run_id="demo123", run_at=datetime.now(UTC), total=100, matched=94,
        exceptions=6, match_rate=Decimal("0.9400"), unmatched_bank_credits=2,
        results=[exc], llm_summary="94 of 100 matched. 6 exceptions found. Investigate.",
    )


def test_docx_report_is_valid_zip_with_content():
    data = generate_docx_recon_report(run())
    assert data[:2] == b"PK"  # docx is a zip
    text = " ".join(
        zipfile.ZipFile(BytesIO(data)).read(n).decode("utf-8", "ignore")
        for n in zipfile.ZipFile(BytesIO(data)).namelist()
    )
    for token in ("TXN1042", "MISSING_BANK_CREDIT", "94 / 100", "demo123",
                  "Settlement pending", "deterministic engine"):
        assert token in text, token


def test_pdf_report_magic_and_nonempty():
    data = generate_pdf_recon_report(run())
    assert data[:5] == b"%PDF-" and len(data) > 1000
