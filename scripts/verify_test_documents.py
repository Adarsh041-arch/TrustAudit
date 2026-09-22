"""Verify the 5 generated test documents against TrustAudit's deterministic validators."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from decimal import Decimal

from audit_v2.domain.catalog_loader import load_catalog
from audit_v2.domain.models import DocumentType, CheckContext
from audit_v2.domain.validators.arithmetic import (
    check_line_total,
    check_subtotal_tieout,
    check_tax_rate,
    check_tax_calculation,
    check_grand_total,
    check_rounding_accumulation,
)
from audit_v2.domain.validators.format_completeness import (
    check_mandatory_fields,
    check_line_item_fields,
    check_currency_format,
)
from audit_v2.domain.validators.reference_integrity import (
    check_po_reference,
    check_gstin_format,
    check_hsn_code,
    check_bank_details,
)
from audit_v2.extraction.invoice_extractor import InvoiceExtractor
from audit_v2.extraction.po_extractor import POExtractor
from audit_v2.extraction.delivery_challan_extractor import DeliveryChallanExtractor

DOCS_DIR = Path(__file__).resolve().parent.parent / "sample_docs" / "test_rules_batch"
CATALOG = load_catalog()
CHECK_MAP = {c.check_id: c for c in CATALOG.checks}

print(f"Loaded {len(CATALOG.checks)} catalog checks.\n")

VALIDATORS_BY_DOC_TYPE = {
    DocumentType.INVOICE: [
        ("CHK-ARITH-LINE-001", check_line_total),
        ("CHK-ARITH-SUBTOTAL-001", check_subtotal_tieout),
        ("CHK-ARITH-TAX-001", check_tax_rate),
        ("CHK-ARITH-TAX-002", check_tax_calculation),
        ("CHK-ARITH-GRAND-001", check_grand_total),
        ("CHK-FORMAT-MANDATORY-001", check_mandatory_fields),
        ("CHK-FORMAT-MANDATORY-002", check_line_item_fields),
        ("CHK-REF-PO-001", check_po_reference),
        ("CHK-REF-GST-001", check_gstin_format),
        ("CHK-REF-HSN-001", check_hsn_code),
        ("CHK-REF-BANK-001", check_bank_details),
    ],
    DocumentType.PURCHASE_ORDER: [
        ("CHK-ARITH-LINE-001", check_line_total),
        ("CHK-FORMAT-MANDATORY-001", check_mandatory_fields),
        ("CHK-FORMAT-MANDATORY-002", check_line_item_fields),
    ],
    DocumentType.DELIVERY_CHALLAN: [
        ("CHK-FORMAT-MANDATORY-001", check_mandatory_fields),
        ("CHK-FORMAT-MANDATORY-002", check_line_item_fields),
    ],
}

pdf_files = sorted(DOCS_DIR.glob("*.pdf"))

summary_records = []

for pdf_path in pdf_files:
    pdf_bytes = pdf_path.read_bytes()
    name = pdf_path.name

    if "PurchaseOrder" in name:
        doc_type = DocumentType.PURCHASE_ORDER
        extractor = POExtractor()
    elif "DeliveryChallan" in name:
        doc_type = DocumentType.DELIVERY_CHALLAN
        extractor = DeliveryChallanExtractor()
    else:
        doc_type = DocumentType.INVOICE
        extractor = InvoiceExtractor()

    extracted = extractor.extract(pdf_bytes, "application/pdf")
    extracted.document_id = pdf_path.stem
    extracted.tenant_id = "test-tenant"
    extracted.doc_type = doc_type

    print(f"==================================================")
    print(f"Document: {name}")
    print(f"Type: {doc_type.value.upper()}")
    print(f"Vendor: {extracted.header.vendor_name.value if extracted.header.vendor_name else None}")
    date_val = (extracted.header.invoice_date.value if extracted.header.invoice_date 
                else (extracted.header.order_date.value if extracted.header.order_date 
                else (extracted.header.delivery_date.value if extracted.header.delivery_date else None)))
    print(f"Date: {date_val}")
    print(f"Grand Total: {extracted.header.grand_total.value if extracted.header.grand_total else None}")
    print(f"Line Items Extracted: {len(extracted.line_items)}")
    for li in extracted.line_items:
        print(f"   Line {li.line_number}: {li.description.value if li.description else '?'} | Qty: {li.quantity.value if li.quantity else '?'} | Rate: {li.unit_price.value if li.unit_price else '?'} | Total: {li.line_total.value if li.line_total else '?'}")

    passed_checks = []
    failed_checks = []
    skipped_checks = []

    validators = VALIDATORS_BY_DOC_TYPE.get(doc_type, [])
    for check_id, validator_fn in validators:
        check_entry = CHECK_MAP.get(check_id)
        if not check_entry:
            continue
        ctx = CheckContext(
            document=extracted,
            check_entry=check_entry,
            currency_exponent=Decimal("0.01"),
        )
        result = validator_fn(ctx)
        if result.status.value == "PASS":
            passed_checks.append(check_id)
        elif result.status.value == "FAIL":
            failed_checks.append((check_id, result.message))
        else:
            skipped_checks.append((check_id, result.message))

    print(f"\nAudit Outcome:")
    if failed_checks:
        overall_status = "FAIL"
        print(f"  [FAIL] OVERALL: FAIL ({len(failed_checks)} critical defect(s) found)")
        for cid, msg in failed_checks:
            print(f"     Defect: [{cid}] {msg}")
    else:
        overall_status = "PASS"
        print(f"  [PASS] OVERALL: PASS (All {len(passed_checks)} applicable checks satisfied)")

    print(f"  Passed Checks ({len(passed_checks)}): {', '.join(passed_checks)}")
    if skipped_checks:
        print(f"  N/A Checks ({len(skipped_checks)}): {', '.join(c[0] for c in skipped_checks)}")
    print()

    summary_records.append({
        "file": name,
        "type": doc_type.value,
        "status": overall_status,
        "passed_count": len(passed_checks),
        "failed_checks": [f"[{cid}] {msg}" for cid, msg in failed_checks],
    })

print("\n" + "="*65)
print("                       FINAL BATCH SUMMARY")
print("="*65)
for r in summary_records:
    status_icon = "[PASS]" if r["status"] == "PASS" else "[FAIL]"
    print(f"{status_icon:6s} | {r['file']}")
    if r["failed_checks"]:
        for fc in r["failed_checks"]:
            print(f"          |- {fc}")
print("="*65)
