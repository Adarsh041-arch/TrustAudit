"""Grounded, presentation-only summary behavior."""
from __future__ import annotations

import pytest

from audit_v2.domain.models import (
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
)
from audit_v2.pipeline.summaries import (
    deterministic_executive_summary,
    generate_document_summary,
)
from audit_v2.server import enrich_document


def _document(doc_type: DocumentType) -> ExtractedDocument:
    return ExtractedDocument(
        document_id=f"doc-{doc_type.value}",
        tenant_id="tenant",
        doc_type=doc_type,
        header=DocumentHeader(document_id=f"doc-{doc_type.value}", doc_type=doc_type),
        coverage=Coverage(pages_total=1, pages_examined=1, coverage_complete=True),
        page_count=1,
        extractor_version="test",
    )


@pytest.mark.parametrize("doc_type", list(DocumentType))
def test_every_supported_document_type_has_deterministic_summary(
    doc_type: DocumentType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    summary = generate_document_summary(
        _document(doc_type), [], status="READY", score=100.0, risk_level="Low Risk",
    )

    assert summary
    assert doc_type.value.replace("_", " ") in summary
    assert "100.0%" in summary


def test_batch_executive_totals_match_document_states() -> None:
    documents = [
        {
            "passed": True, "document_status": "READY",
            "risk_level": "Low Risk", "human_review_recommended": False,
        },
        {
            "passed": False, "document_status": "READY",
            "risk_level": "High Risk", "human_review_recommended": True,
        },
        {
            "passed": False, "document_status": "INCOMPLETE",
            "risk_level": "High Risk", "human_review_recommended": True,
        },
    ]

    summary = deterministic_executive_summary(documents)
    assert "3 document(s)" in summary
    assert "1 passed" in summary
    assert "1 failed" in summary
    assert "1 remain incomplete" in summary
    assert "2 document(s) are high risk" in summary
    assert "2 require human review" in summary


def test_incomplete_document_cannot_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    document = _document(DocumentType.INVOICE)
    document.coverage = Coverage(
        pages_total=2,
        pages_examined=1,
        pages_unreadable=[2],
        coverage_complete=False,
    )

    result = enrich_document(document, "incomplete.pdf", [], b"", "application/pdf")
    assert result["score"] == 100.0
    assert result["document_status"] == "INCOMPLETE"
    assert result["passed"] is False
    assert result["human_review_recommended"] is True


def test_deterministic_summary_mode_never_calls_nvidia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "configured-but-not-used")
    monkeypatch.setenv("V2_SUMMARY_MODE", "deterministic")

    class ForbiddenGateway:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("NVIDIA summary gateway must not be constructed")

    monkeypatch.setattr(
        "audit_v2.pipeline.summaries.NvidiaGateway", ForbiddenGateway
    )
    summary = generate_document_summary(
        _document(DocumentType.INVOICE), [], status="READY",
        score=100.0, risk_level="Low Risk",
    )
    assert "100.0%" in summary
