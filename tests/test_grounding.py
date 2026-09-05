"""Unit tests for page-level GLM-OCR grounding."""
from __future__ import annotations

from audit_v2.extraction.grounding import ground_instance
from audit_v2.extraction.schemas import ContractExtraction, InvoiceExtraction


def test_identifier_suffix_cannot_become_amount() -> None:
    candidate = InvoiceExtraction(invoice_number="SC-2026-118", grand_total="118.00")
    grounded = ground_instance(candidate, "SERVICE CONTRACT SC-2026-118", page=1)

    assert grounded.instance.invoice_number == "SC-2026-118"
    assert grounded.instance.grand_total is None
    assert any(issue.field == "grand_total" for issue in grounded.issues)


def test_currency_and_indian_separator_amounts_are_equivalent() -> None:
    candidate = InvoiceExtraction(subtotal="123456.78", grand_total="123456.78")
    grounded = ground_instance(
        candidate,
        "Subtotal INR 1,23,456.78  Grand Total ₹1,23,456.78",
        page=1,
    )

    assert grounded.instance.subtotal == "123456.78"
    assert grounded.instance.grand_total == "123456.78"
    assert grounded.issues == []


def test_equivalent_date_identifier_and_normalized_name_are_grounded() -> None:
    candidate = InvoiceExtraction(
        vendor_name="ACME & Sons Pvt. Ltd.",
        invoice_number="INV/009-A",
        invoice_date="2026-07-15",
    )
    grounded = ground_instance(
        candidate,
        "Acme and Sons Pvt Ltd | Invoice: INV/009-A | Date 15 July 2026",
        page=2,
    )

    # Punctuation and case differences are accepted; lexical changes are not.
    assert grounded.instance.vendor_name is None
    assert grounded.instance.invoice_number == "INV/009-A"
    assert grounded.instance.invoice_date == "2026-07-15"
    assert grounded.issues[0].page == 2


def test_partial_line_item_is_discarded_as_a_whole() -> None:
    candidate = InvoiceExtraction.model_validate(
        {
            "line_items": [
                {
                    "description": "Widget",
                    "quantity": "2",
                    "unit_price": "100.00",
                    "line_total": "200.00",
                }
            ]
        }
    )
    grounded = ground_instance(candidate, "Widget 2 100.00", page=1)

    assert grounded.instance.line_items == []
    assert any(
        "line item is not fully grounded" in issue.reason
        for issue in grounded.issues
    )


def test_contract_date_cannot_be_relabelled_as_expiry() -> None:
    candidate = ContractExtraction(
        effective_date="2026-07-20",
        expiry_date="2026-07-20",
    )
    transcript = "This Sales Contract is made on 20 July 2026"

    grounded = ground_instance(candidate, transcript, page=1)

    assert grounded.instance.effective_date == "2026-07-20"
    assert grounded.instance.expiry_date is None
    assert any(issue.field == "expiry_date" for issue in grounded.issues)


def test_explicitly_labelled_contract_expiry_is_grounded() -> None:
    candidate = ContractExtraction(expiry_date="2027-07-20")
    grounded = ground_instance(candidate, "Valid Until: 20 July 2027", page=1)

    assert grounded.instance.expiry_date == "2027-07-20"
    assert grounded.issues == []
