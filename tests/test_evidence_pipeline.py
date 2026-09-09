"""Tests for the evidence pipeline (new_requirements.md §3–§4, plan §8).

Covers the spec's evidence ladder for math-heavy docs — regex → OCR → GLM raw
transcription → grounded structure → arithmetic → metadata — grounding review
flags, and the Decimal arithmetic evidence values. All network + OCR is mocked
via the injected gateway / ``ocr=`` seam, so these run fully offline.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from audit_v2.domain.evidence import EvidenceNature
from audit_v2.domain.models import (
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
    LineItem,
    ProvenancedValue,
)
from audit_v2.pipeline.evidence_pipeline import (
    _compute_arithmetic,
    run_document_pipeline,
)

PIPELINE = "audit_v2.pipeline.evidence_pipeline"


def _pv(value: str, currency: str | None = None) -> ProvenancedValue:
    return ProvenancedValue(
        value=value, raw=value, page=1, confidence=0.99, currency=currency
    )


@pytest.fixture
def _one_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the pipeline one page image and no regex read, so the VLM branch is
    the only field source and the evidence ordering is deterministic."""
    monkeypatch.setattr(
        f"{PIPELINE}.render_pages_to_jpeg", lambda *a, **k: [b"jpg"]
    )
    monkeypatch.setattr(
        f"{PIPELINE}._run_regex", lambda *a, **k: (None, "regex stubbed")
    )


_CONSISTENT_INVOICE = json.dumps(
    {
        "invoice_number": "INV-1",
        "vendor_name": "Acme",
        "invoice_date": "2026-07-15",
        "subtotal": "250.00",
        "grand_total": "250.00",
        "line_items": [
            {
                "description": "Widget", "quantity": "2",
                "unit_price": "100.00", "line_total": "200.00",
            },
            {
                "description": "Gadget", "quantity": "1",
                "unit_price": "50.00", "line_total": "50.00",
            },
        ],
        "tax_lines": [],
        "other_necessary_details": [],
    }
)

_CONSISTENT_TRANSCRIPT = """COMMERCIAL INVOICE
Vendor: Acme
Invoice No: INV-1
Date: 2026-07-15
| Description | Quantity | Unit Price (USD) | Amount (USD) |
| Widget | 2 | 100.00 | 200.00 |
| Gadget | 1 | 50.00 | 50.00 |
| Total Invoice Value (USD) | | | 250.00 |"""


def test_math_pipeline_evidence_order(_one_page, make_gateway) -> None:
    """regex → OCR → GLM transcription → structure → arithmetic → metadata."""
    gateway = make_gateway(_CONSISTENT_TRANSCRIPT, _CONSISTENT_INVOICE)
    result = run_document_pipeline(
        data=b"x",
        mime_type="application/pdf",
        document_id="doc1",
        tenant_id="t",
        vlm_gateway=gateway,
    )

    order = [(e.nature, e.source) for e in result.evidences]
    assert order == [
        (EvidenceNature.OCR_REGEX_OBSERVATIONS, "regex"),
        (EvidenceNature.OCR_REGEX_OBSERVATIONS, "glm_ocr_transcription"),
        (EvidenceNature.VLM_OBSERVATIONS, "glm_ocr_transcript_deterministic"),
        (EvidenceNature.OCR_REGEX_OBSERVATIONS, "rapidocr"),
        (EvidenceNature.ARITHMETIC_COMPUTATION, "arithmetic"),
        (EvidenceNature.METADATA, "metadata"),
    ]
    # Consistent, fully grounded doc → no human review; cross-check skipped offline.
    assert result.requires_human_review is False
    assert result.contradictions == []
    assert len(gateway.calls) == 1
    assert result.document.extraction_strategy == "transcript_only"
    arith = next(e for e in result.evidences if e.source == "arithmetic")
    assert Decimal(arith.payload["total_quantity"]) == Decimal(3)
    assert Decimal(arith.payload["computed_line_items_total"]) == Decimal("250.00")


def test_metadata_evidence_is_always_last(_one_page, make_gateway) -> None:
    result = run_document_pipeline(
        data=b"x", mime_type="application/pdf", document_id="doc1",
        tenant_id="t",
        vlm_gateway=make_gateway(_CONSISTENT_TRANSCRIPT, _CONSISTENT_INVOICE),
    )
    last = result.evidences[-1]
    assert last.nature == EvidenceNature.METADATA
    assert last.source == "metadata"
    assert last.payload["doc_type"] == DocumentType.INVOICE.value


class _FieldOcr:
    """OCR double that reports an available grand_total, to force a self-check."""

    def __init__(self, grand_total: str) -> None:
        self._grand_total = grand_total

    def extract_text(self, images):
        from audit_v2.extraction.ocr_extractor import OcrPageText, OcrResult

        return OcrResult(
            available=True,
            pages=[OcrPageText(
                page=1, lines=[f"Grand Total {self._grand_total}"],
                mean_confidence=0.9,
            )],
        )

    def extract_fields(self, images, doc_type) -> dict:
        return {
            "available": True,
            "mean_confidence": 0.9,
            "po_reference": None,
            "gstins": [],
            "grand_total": self._grand_total,
            "amount_candidates": [self._grand_total],
        }


def test_unsupported_glm_candidate_marks_human_review(_one_page, make_gateway) -> None:
    """A structured amount absent from the transcript is rejected and reviewed."""
    initial = json.dumps(
        {
            "invoice_number": "INV-1",
            "grand_total": "9999.00",
            "line_items": [
                {
                    "description": "Widget", "quantity": "1",
                    "unit_price": "9999.00", "line_total": "9999.00",
                }
            ],
            "tax_lines": [],
            "other_necessary_details": [],
        }
    )
    transcript = "Invoice INV-1\nWidget 1 1000.00 1000.00\nGrand Total 1000.00"
    gateway = make_gateway(transcript, initial)
    result = run_document_pipeline(
        data=b"x", mime_type="application/pdf", document_id="doc2",
        tenant_id="t", doc_type=DocumentType.INVOICE,
        vlm_gateway=gateway, ocr=_FieldOcr("1000.00"),
    )

    sources = [e.source for e in result.evidences]
    assert sources[:4] == [
        "regex", "glm_ocr_transcription",
        "glm_ocr_transcript_deterministic", "glm_ocr_structured",
    ]
    assert "rapidocr" in sources
    assert sources.count("grounding_rejection") >= 1
    assert sources[-2:] == ["arithmetic", "metadata"]
    assert result.requires_human_review is True
    assert result.document.header.grand_total.decimal_value == Decimal("1000.00")
    assert len(gateway.calls) == 2
    assert result.document.structured_fallback_used is True


def test_fully_grounded_glm_needs_no_review(_one_page, make_gateway) -> None:
    """When GLM fields are visible in the transcript, grounding does not review."""
    gateway = make_gateway(_CONSISTENT_TRANSCRIPT, _CONSISTENT_INVOICE)
    result = run_document_pipeline(
        data=b"x", mime_type="application/pdf", document_id="doc3",
        tenant_id="t", vlm_gateway=gateway, ocr=_FieldOcr("250.00"),
    )
    assert "grounding_rejection" not in [e.source for e in result.evidences]
    assert result.requires_human_review is False
    assert len(gateway.calls) == 1


def test_clean_document_skips_nvidia_cross_check(
    _one_page, make_gateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "configured-but-must-not-be-used")
    vision = make_gateway(_CONSISTENT_TRANSCRIPT)
    text = make_gateway()
    result = run_document_pipeline(
        data=b"x", mime_type="application/pdf", document_id="doc_fast",
        tenant_id="t", vlm_gateway=vision, text_gateway=text,
    )
    assert result.document.extraction_strategy == "transcript_only"
    assert len(vision.calls) == 1
    assert text.calls == []


def test_qwen_contract_uses_one_transcript_call_without_expiry(
    _one_page, make_gateway
) -> None:
    transcript = """SALES CONTRACT
CONTRACT NO.: SC-2026-118
This Sales Contract is made on 20 July 2026
BETWEEN
ABC Agro Exports Pvt. Ltd.
AND
Green Valley Foods LLC"""
    gateway = make_gateway(transcript)
    gateway.backend = "qwen_ollama"
    result = run_document_pipeline(
        data=b"image",
        mime_type="image/jpeg",
        document_id="doc_contract",
        tenant_id="t",
        doc_type=DocumentType.CONTRACT,
        vlm_gateway=gateway,
    )

    assert result.document is not None
    assert result.document.header.vendor_name.value == "ABC Agro Exports Pvt. Ltd."
    assert result.document.header.buyer_name.value == "Green Valley Foods LLC"
    assert result.document.header.invoice_date.value == "2026-07-20"
    assert result.document.header.expiry_date is None
    assert result.document.extraction_strategy == "transcript_only"
    assert result.document.vision_backend == "qwen_ollama"
    assert result.document.vision_call_count == 1
    assert result.document.glm_call_count == 0
    assert len(gateway.calls) == 1


def test_certificate_of_origin_is_not_audited_as_invoice(
    _one_page, make_gateway
) -> None:
    transcript = """CERTIFICATE OF ORIGIN (Non-Preferential)
Certificate No.: COO-2026-217
Date: 18 August 2026
Exporter ABC Agro Exports Pvt. Ltd.
Consignee Green Valley Foods LLC
originated in India
Premium Basmati Rice 5% Broken 10063020 500 MT INV-2026-453 18.08.2026"""
    structured = json.dumps({
        "certificate_number": "COO-2026-217",
        "exporter_name": "ABC Agro Exports Pvt. Ltd.",
        "country_of_origin": "India",
        "signature_present": True,
        "seal_present": True,
        "goods": [{
            "description": "Premium Basmati Rice 5% Broken",
            "hs_code": "10063020",
            "quantity": "500 MT",
            "quantity_unit": None,
            "invoice_number": "INV-2026-453",
            "invoice_date": "18.08.2026",
        }],
        "other_necessary_details": [],
    })
    result = run_document_pipeline(
        data=b"image", mime_type="image/jpeg", document_id="doc_coo",
        tenant_id="t", vlm_gateway=make_gateway(transcript, structured),
    )

    assert result.doc_type == DocumentType.CERTIFICATE_OF_ORIGIN
    assert result.document is not None
    assert result.document.classification_status.value == "CONFIRMED"
    assert result.document.header.certificate_number.value == "COO-2026-217"
    assert result.document.header.referenced_invoice_number.value == "INV-2026-453"
    assert result.document.header.grand_total is None
    assert len(result.document.certificate_goods) == 1


def test_pipeline_degrades_without_vlm_or_ocr() -> None:
    """No gateway, OCR unavailable (autouse stub), regex-only: still succeeds."""
    result = run_document_pipeline(
        data=b"not a real pdf", mime_type="application/pdf",
        document_id="doc4", tenant_id="t", doc_type=DocumentType.INVOICE,
    )
    sources = [e.source for e in result.evidences]
    # No VLM evidence (no gateway); OCR present-but-unavailable; metadata last.
    assert "vlm" not in sources
    assert sources[-1] == "metadata"
    assert result.contradictions == []


def _doc_for_arithmetic() -> ExtractedDocument:
    li1 = LineItem(
        line_number=1, description=_pv("Widget"), quantity=_pv("2"),
        unit_price=_pv("100.00", "USD"), line_total=_pv("200.00", "USD"),
    )
    li2 = LineItem(
        line_number=2, description=_pv("Gadget"), quantity=_pv("1"),
        unit_price=_pv("50.00", "USD"), line_total=_pv("50.00", "USD"),
    )
    return ExtractedDocument(
        document_id="doc_a", tenant_id="t", doc_type=DocumentType.INVOICE,
        header=DocumentHeader(
            document_id="doc_a", doc_type=DocumentType.INVOICE,
            subtotal=_pv("250.00", "USD"), grand_total=_pv("250.00", "USD"),
        ),
        line_items=[li1, li2],
        coverage=Coverage(pages_total=1, pages_examined=1, coverage_complete=True),
        page_count=1, extractor_version="test",
    )


def test_compute_arithmetic_values() -> None:
    """§4 arithmetic evidence: quantities summed, line totals computed vs stated."""
    payload = _compute_arithmetic(_doc_for_arithmetic())
    assert Decimal(payload["total_quantity"]) == Decimal(3)
    assert Decimal(payload["computed_line_items_total"]) == Decimal("250.00")
    assert Decimal(payload["stated_line_items_total"]) == Decimal("250.00")
    assert Decimal(payload["tax_total"]) == Decimal(0)
    assert Decimal(payload["expected_grand_total"]) == Decimal("250.00")
    assert Decimal(payload["stated_grand_total"]) == Decimal("250.00")


def test_compute_arithmetic_detects_line_mismatch() -> None:
    """A stated line total that differs from qty×price is reflected in the sums."""
    li = LineItem(
        line_number=1, description=_pv("Widget"), quantity=_pv("2"),
        unit_price=_pv("100.00", "USD"), line_total=_pv("999.00", "USD"),
    )
    doc = ExtractedDocument(
        document_id="doc_b", tenant_id="t", doc_type=DocumentType.INVOICE,
        header=DocumentHeader(document_id="doc_b", doc_type=DocumentType.INVOICE),
        line_items=[li],
        coverage=Coverage(pages_total=1, pages_examined=1, coverage_complete=True),
        page_count=1, extractor_version="test",
    )
    payload = _compute_arithmetic(doc)
    assert Decimal(payload["computed_line_items_total"]) == Decimal("200.00")
    assert Decimal(payload["stated_line_items_total"]) == Decimal("999.00")
