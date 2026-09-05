"""Tests for the RapidOCR wrapper (new_requirements.md §3, plan §8).

Two paths: graceful degradation when ``rapidocr-onnxruntime`` is absent (never
crash, ``available=False``), and the field-extraction logic driven by a mocked
engine so no ONNX models are loaded.
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal

import pytest

from audit_v2.domain.models import DocumentType
from audit_v2.extraction import ocr_extractor
from audit_v2.extraction.ocr_extractor import RapidOcrExtractor
from audit_v2.extraction.parser import extract_po_reference

_HAS_RAPIDOCR = importlib.util.find_spec("rapidocr_onnxruntime") is not None


@pytest.mark.skipif(
    _HAS_RAPIDOCR,
    reason="rapidocr installed; this covers the absent path",
)
def test_get_engine_none_when_package_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reset the module-level engine cache; monkeypatch restores it afterwards.
    monkeypatch.setattr(ocr_extractor, "_ENGINE", None)
    monkeypatch.setattr(ocr_extractor, "_ENGINE_TRIED", False)
    monkeypatch.setattr(ocr_extractor, "_ENGINE_ERROR", None)

    assert ocr_extractor._get_engine() is None
    assert ocr_extractor._ENGINE_ERROR is not None
    assert "not installed" in ocr_extractor._ENGINE_ERROR

    # Public API degrades gracefully, never raising.
    text_res = RapidOcrExtractor().extract_text([b"page"])
    assert text_res.available is False
    fields = RapidOcrExtractor().extract_fields([b"page"], DocumentType.INVOICE)
    assert fields["available"] is False


def test_extract_text_mocked_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_engine(_img):
        raw = [
            [[[0, 0], [1, 0], [1, 1], [0, 1]], "Grand Total Rs. 1,250.00", 0.95],
            [[[0, 0], [1, 0], [1, 1], [0, 1]], "Vendor: Acme Industries", 0.90],
        ]
        return raw, 0.02

    monkeypatch.setattr(ocr_extractor, "_get_engine", lambda: _fake_engine)

    res = RapidOcrExtractor().extract_text([b"page"])
    assert res.available is True
    assert res.pages[0].lines == ["Grand Total Rs. 1,250.00", "Vendor: Acme Industries"]
    assert res.mean_confidence == pytest.approx(0.925)


def test_extract_fields_mocked_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    text_lines = ["Grand Total Rs. 1,250.00", "Vendor: Acme Industries"]

    def _fake_engine(_img):
        raw = [[[[0, 0], [1, 0], [1, 1], [0, 1]], line, 0.95] for line in text_lines]
        return raw, 0.02

    monkeypatch.setattr(ocr_extractor, "_get_engine", lambda: _fake_engine)

    fields = RapidOcrExtractor().extract_fields([b"page"], DocumentType.INVOICE)
    assert fields["available"] is True
    # The explicit label, not numeric magnitude, anchors the grand total.
    assert Decimal(fields["grand_total"]) == Decimal("1250.00")
    assert any(Decimal(a) == Decimal("1250.00") for a in fields["amount_candidates"])
    # po_reference is whatever the regex utility pulls from the same text.
    assert fields["po_reference"] == extract_po_reference("\n".join(text_lines))


def test_amounts_ignores_small_integers() -> None:
    # Line numbers / quantities / years below 100 must not become the anchor.
    amounts = RapidOcrExtractor._amounts("Item 1 Qty 2 Total 5,400.00 Ref 42")
    assert Decimal("5400.00") in amounts
    assert all(a >= Decimal(100) for a in amounts)


def test_certificate_numbers_never_become_total_or_po(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines = [
        "CERTIFICATE OF ORIGIN", "Exporter ABC Agro Exports", "HS Code 10063020",
        "Quantity 500 MT", "Invoice No. INV-2026-453",
    ]

    def _fake_engine(_img):
        return [[[[0, 0], [1, 0], [1, 1], [0, 1]], line, 0.95] for line in lines], 0.02

    monkeypatch.setattr(ocr_extractor, "_get_engine", lambda: _fake_engine)
    fields = RapidOcrExtractor().extract_fields(
        [b"page"], DocumentType.CERTIFICATE_OF_ORIGIN
    )
    assert fields["grand_total"] is None
    assert fields["po_reference"] is None
