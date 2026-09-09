"""Transcript-first extraction regressions for tabular documents."""
from decimal import Decimal

from audit_v2.domain.models import DocumentType
from audit_v2.extraction.grounding import ground_instance
from audit_v2.extraction.schemas import to_extracted_document
from audit_v2.extraction.transcript_parser import parse_transcript


INVOICE = """COMMERCIAL INVOICE
ABC Agro Exports Pvt. Ltd.
120, Agro House, J. P. Road, Andheri (West), Mumbai - 400058, India
GSTIN: 27AANCA1254B1Z5
Invoice No: INV-2026-453
Date: 18 August 2026
Buyer
Green Valley Foods LLC
P.O. Box: 123456, Dubai, United Arab Emirates
VAT No.: UAE5487654321
| Description of Goods | HS Code | Quantity | Unit Price (USD) | Amount (USD) |
| Premium Basmati Rice 5% Broken | 10063020 | 500 MT | 1,050.00 | 525,000.00 |
| Total Invoice Value (USD) | | | | 525,000.00 |
Amount in Words: USD Five Hundred Twenty Five Thousand Only
"""


def test_supplied_commercial_invoice_is_complete_without_model_recovery() -> None:
    parsed = parse_transcript(DocumentType.INVOICE, INVOICE, first_page=True)
    assert parsed.fallback_reasons == []
    grounded = ground_instance(parsed.instance, INVOICE, 1)
    assert grounded.issues == []
    doc = to_extracted_document(
        grounded.instance, document_id="doc_invoice", tenant_id="t",
        doc_type=DocumentType.INVOICE, page_count=1,
    )
    assert doc.header.vendor_name.value == "ABC Agro Exports Pvt. Ltd."
    assert doc.header.buyer_name.value == "Green Valley Foods LLC"
    assert doc.header.invoice_number.value == "INV-2026-453"
    assert doc.header.invoice_date.value == "2026-08-18"
    assert doc.header.grand_total.decimal_value == Decimal("525000.00")
    assert doc.header.grand_total.currency == "USD"
    line = doc.line_items[0]
    assert line.hsn_sac.value == "10063020"
    assert line.quantity.decimal_value == Decimal("500")
    assert line.quantity_unit.value == "MT"
    assert line.unit_price.decimal_value == Decimal("1050.00")
    assert line.unit_price.currency == "USD"
    assert line.line_total.decimal_value == Decimal("525000.00")
    assert line.expected_total() == Decimal("525000.00")


def test_multiple_explicit_totals_are_ambiguous_not_guessed() -> None:
    text = INVOICE.replace(
        "Amount in Words:", "Grand Total: 500,000.00\nAmount in Words:"
    )
    parsed = parse_transcript(DocumentType.INVOICE, text, first_page=True)
    assert parsed.instance.grand_total is None
    assert "ambiguous:grand_total" in parsed.fallback_reasons


def test_purchase_order_uses_same_transcript_first_contract() -> None:
    text = """PURCHASE ORDER
Vendor: Acme Supplies Ltd.
PO No: PO-2026-118
Order Date: 18 August 2026
| Item | Quantity | Unit Price (INR) | Amount (INR) |
| Widget | 2 | 100.00 | 200.00 |
"""
    parsed = parse_transcript(DocumentType.PURCHASE_ORDER, text, first_page=True)
    assert parsed.fallback_reasons == []
    assert parsed.instance.po_number == "PO-2026-118"
    assert len(parsed.instance.line_items) == 1


def test_qwen_invoice_transcript_keeps_wrapped_description() -> None:
    transcript = """COMMERCIAL INVOICE
ABC Agro Exports Pvt. Ltd.
Invoice No.: INV-2026-453
Date: 18 August 2026
Buyer
Green Valley Foods LLC
Description of Goods | HS Code | Quantity | Unit Price (USD) | Amount (USD)
Premium Basmati Rice | 10063020 | 500 MT | 1,050.00 | 525,000.00
5% Broken
Total Invoice Value (USD) | 525,000.00
Amount in Words: USD Five Hundred Twenty Five Thousand Only"""

    parsed = parse_transcript(DocumentType.INVOICE, transcript, first_page=True)

    assert parsed.complete is True
    assert len(parsed.instance.line_items) == 1
    assert parsed.instance.line_items[0].description == (
        "Premium Basmati Rice 5% Broken"
    )


def test_qwen_contract_transcript_is_complete_without_inventing_expiry() -> None:
    transcript = """SALES CONTRACT
CONTRACT NO.: SC-2026-118
This Sales Contract is made on 20 July 2026
BETWEEN
ABC Agro Exports Pvt. Ltd.,
120, Agro House, J. P. Road,
(Hereinafter referred to as \"SELLER\")
AND
Green Valley Foods LLC,
P.O. Box: 123456, Dubai, United Arab Emirates
(Hereinafter referred to as \"BUYER\")"""

    parsed = parse_transcript(DocumentType.CONTRACT, transcript, first_page=True)

    assert parsed.complete is True
    assert parsed.instance.reference == "SC-2026-118"
    assert parsed.instance.party_a == "ABC Agro Exports Pvt. Ltd."
    assert parsed.instance.party_b == "Green Valley Foods LLC"
    assert parsed.instance.effective_date == "2026-07-20"
    assert parsed.instance.expiry_date is None


def test_qwen_labelled_contract_pdf_transcript_is_complete() -> None:
    transcript = """| INTERNATIONAL SALES CONTRACT |
| Contract No. | SC-2026-118 |
| Contract Date | 03 August 2026 |
| Seller | ABC Agro Exports Pvt. Ltd., Mumbai, India |
| Buyer | Green Valley Foods LLC, Dubai, UAE |
Seller shall provide Commercial Invoice and Certificate of Origin."""

    parsed = parse_transcript(DocumentType.CONTRACT, transcript, first_page=True)

    assert parsed.complete is True
    assert parsed.instance.reference == "SC-2026-118"
    assert parsed.instance.party_a == "ABC Agro Exports Pvt. Ltd., Mumbai, India"
    assert parsed.instance.party_b == "Green Valley Foods LLC, Dubai, UAE"
    assert parsed.instance.effective_date == "2026-08-03"
    assert parsed.instance.expiry_date is None


def test_qwen_proforma_markdown_labels_parse_without_structured_fallback() -> None:
    transcript = """| PROFORMA INVOICE |
| Proforma Invoice No. | PI-2026-453 |
| Date | 04 August 2026 |
| Seller | ABC Agro Exports Pvt. Ltd., Mumbai, India |
| Buyer | Green Valley Foods LLC, Dubai, UAE |"""

    parsed = parse_transcript(DocumentType.CONTRACT, transcript, first_page=True)

    assert parsed.complete is True
    assert parsed.instance.reference == "PI-2026-453"
    assert parsed.instance.effective_date == "2026-08-04"


def test_delivery_challan_rows_do_not_require_prices() -> None:
    transcript = """DELIVERY CHALLAN
Dispatch From: NewTech Solutions Pvt Ltd
Challan No: DC-2026-0011
Date: 15 June 2026
PO Reference: PO-2026-485
| Description | HSN | Quantity |
| Paper Shredder | 8472 | 3 Nos |
| External Hard Drive 2TB | 8523 | 6 Nos |
"""
    parsed = parse_transcript(DocumentType.DELIVERY_CHALLAN, transcript, first_page=True)
    grounded = ground_instance(parsed.instance, transcript, page=1)

    assert parsed.fallback_reasons == []
    assert len(grounded.instance.line_items) == 2
    assert grounded.issues == []


def test_business_letter_uses_labelled_sender_and_date() -> None:
    transcript = """BUSINESS LETTER
Letter No: LTR-2026-0018
Date: 12 July 2026
From: Shree Ganesh Traders Pvt. Ltd.
To: Skyline Infra Projects Ltd.
Subject: Quotation Submission
"""
    parsed = parse_transcript(DocumentType.LETTER, transcript, first_page=True)

    assert parsed.fallback_reasons == []
    assert parsed.instance.sender == "Shree Ganesh Traders Pvt. Ltd."
    assert parsed.instance.recipient == "Skyline Infra Projects Ltd."
    assert parsed.instance.date == "2026-07-12"
