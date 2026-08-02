from __future__ import annotations

import pytest

from audit_v2.domain.models import DocumentType
from audit_v2.extraction.classifier import (
    EXTRACTOR_REGISTRY,
    classify_document,
    classify_document_from_data,
)


class TestClassifyDocument:
    def test_classify_invoice(self):
        text = "Tax Invoice\nInvoice No: INV-001\nDate: 25/07/2026"
        result, conf = classify_document(text)
        assert result == DocumentType.INVOICE
        assert conf >= 0.8

    def test_classify_po(self):
        text = "Purchase Order\nPO No: PO-001\nVendor: Acme Corp"
        result, conf = classify_document(text)
        assert result == DocumentType.PURCHASE_ORDER
        assert conf >= 0.8

    def test_classify_delivery_challan(self):
        text = "Delivery Challan\nDC No: DC-001\nVehicle No: MH-01-AB-1234"
        result, conf = classify_document(text)
        assert result == DocumentType.DELIVERY_CHALLAN
        assert conf >= 0.8

    def test_classify_grn(self):
        text = "Goods Receipt Note\nGRN No: GRN-001\nMaterial Received"
        result, conf = classify_document(text)
        assert result == DocumentType.GOODS_RECEIPT_NOTE
        assert conf >= 0.8

    def test_classify_empty_returns_low_confidence(self):
        result, conf = classify_document("")
        assert conf < 0.5

    def test_classify_ambiguous_returns_low_confidence(self):
        text = "Some random document with no clear type indicators"
        result, conf = classify_document(text)
        assert conf < 0.5

    def test_classify_from_data_with_text_mime(self):
        data = b"Tax Invoice\nInvoice No: INV-001"
        result, conf = classify_document_from_data(data, "text/plain")
        assert result == DocumentType.INVOICE
        assert conf >= 0.8


class TestExtractorRegistry:
    def test_invoice_in_registry(self):
        assert DocumentType.INVOICE in EXTRACTOR_REGISTRY
        assert EXTRACTOR_REGISTRY[DocumentType.INVOICE] is not None

    def test_po_in_registry(self):
        assert DocumentType.PURCHASE_ORDER in EXTRACTOR_REGISTRY
        assert EXTRACTOR_REGISTRY[DocumentType.PURCHASE_ORDER] is not None

    def test_dc_in_registry(self):
        assert DocumentType.DELIVERY_CHALLAN in EXTRACTOR_REGISTRY
        assert EXTRACTOR_REGISTRY[DocumentType.DELIVERY_CHALLAN] is not None

    def test_grn_in_registry(self):
        assert DocumentType.GOODS_RECEIPT_NOTE in EXTRACTOR_REGISTRY
        assert EXTRACTOR_REGISTRY[DocumentType.GOODS_RECEIPT_NOTE] is not None
