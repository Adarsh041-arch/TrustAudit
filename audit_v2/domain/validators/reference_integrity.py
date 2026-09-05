"""Reference integrity validators — CHK-REF-* checks.

Single-document checks are deterministic over the extracted record. The
cross-document checks (CHK-REF-QTY-001/002) run when a TransactionCluster is
present on the CheckContext (Phase 7) and SKIP otherwise.
"""
import re
from decimal import Decimal

from audit_v2.domain.models import (
    CheckContext,
    CheckResult,
    DocumentType,
    EvidenceItem,
    ExtractedDocument,
    LineItem,
)

GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9][Z][0-9A-Z]$")
IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def check_po_reference(ctx: CheckContext) -> CheckResult:
    """CHK-REF-PO-001 — invoice references a valid PO number."""
    doc = ctx.document
    po_ref = doc.header.po_reference
    if po_ref is None or not po_ref.value.strip():
        return CheckResult.failed(
            "CHK-REF-PO-001",
            expected="PO reference",
            actual="missing",
            delta="N/A",
            message="Invoice has no PO reference",
        )
    return CheckResult.passed("CHK-REF-PO-001")


def _is_international_doc(doc: ExtractedDocument) -> bool:
    all_pvs = [doc.header.grand_total, doc.header.subtotal]
    for li in doc.line_items:
        all_pvs.extend([li.line_total, li.unit_price])
    currencies = {pv.currency.upper() for pv in all_pvs if pv and pv.currency}
    return bool(currencies and not currencies.intersection({"INR", "RS", "RS.", "₹"}))


def check_gstin_format(ctx: CheckContext) -> CheckResult:
    """CHK-REF-GST-001 — GSTIN format is valid (15 chars, alphanumeric)."""
    doc = ctx.document
    gstin = doc.header.vendor_gstin
    if gstin is None or not gstin.value.strip():
        if _is_international_doc(doc):
            return CheckResult.skipped(
                "CHK-REF-GST-001",
                "GSTIN not applicable for non-GST/international document",
            )
        return CheckResult.failed(
            "CHK-REF-GST-001",
            expected="valid GSTIN",
            actual="missing",
            delta="N/A",
            message="GSTIN is missing",
        )
    if not GSTIN_PATTERN.match(gstin.value.strip().upper()):
        return CheckResult.failed(
            "CHK-REF-GST-001",
            expected="valid GSTIN (15 chars: 2 alphanumeric + 5 alpha + 4 numeric + 1 alpha + 1 alphanumeric + Z + 1 alphanumeric)",  # noqa: E501
            actual=gstin.value,
            delta="N/A",
            message=f"GSTIN '{gstin.value}' does not match valid format",
        )
    return CheckResult.passed("CHK-REF-GST-001")


def check_hsn_code(ctx: CheckContext) -> CheckResult:
    """CHK-REF-HSN-001 — HSN/SAC code is present and valid.

    Indian HSN is reported at 4, 6 or 8 digits depending on the filer's
    turnover slab; SAC is 6. Requiring 6/8 rejects legitimate 4-digit headings.
    """
    doc = ctx.document
    for line in doc.line_items:
        if line.hsn_sac is None or not line.hsn_sac.value.strip():
            return CheckResult.failed(
                "CHK-REF-HSN-001",
                expected="4, 6 or 8 digit HSN/SAC",
                actual="missing",
                delta="N/A",
                message=f"Line {line.line_number} missing HSN/SAC code",
            )
        hsn = line.hsn_sac.value.strip()
        if not hsn.isdigit() or len(hsn) not in (4, 6, 8):
            return CheckResult.failed(
                "CHK-REF-HSN-001",
                expected="4, 6 or 8 digit HSN/SAC",
                actual=hsn,
                delta="N/A",
                message=f"HSN/SAC '{hsn}' invalid for line {line.line_number}",
            )
    return CheckResult.passed("CHK-REF-HSN-001")


def check_bank_details(ctx: CheckContext) -> CheckResult:
    """CHK-REF-BANK-001 — bank details (account number, IFSC/SWIFT/IBAN) are present."""
    doc = ctx.document
    bank = doc.header.bank_details
    if bank is None:
        if _is_international_doc(doc):
            return CheckResult.skipped(
                "CHK-REF-BANK-001",
                "Bank details optional for international document",
            )
        return CheckResult.failed(
            "CHK-REF-BANK-001",
            expected="bank details",
            actual="missing",
            delta="N/A",
            message="Bank details are missing",
        )
    missing = []
    has_account = bool(bank.get("account_number") or bank.get("iban"))
    has_code = bool(bank.get("ifsc") or bank.get("swift") or bank.get("bic"))
    if not has_account:
        missing.append("account_number")
    if not has_code and not _is_international_doc(doc):
        missing.append("ifsc")
    if missing:
        return CheckResult.failed(
            "CHK-REF-BANK-001",
            expected="account_number and ifsc",
            actual=f"missing: {', '.join(missing)}",
            delta="N/A",
            message=f"Bank details are incomplete: missing {', '.join(missing)}",
        )
    return CheckResult.passed("CHK-REF-BANK-001")


def _qty_by_desc(doc: ExtractedDocument) -> dict[str, tuple[LineItem, Decimal]]:
    out: dict[str, tuple[LineItem, Decimal]] = {}
    for li in doc.line_items:
        key = li.description.value.strip().casefold()
        prev = out.get(key)
        qty = li.quantity.decimal_value
        out[key] = (li, (prev[1] + qty) if prev else qty)
    return out


def _qty_evidence(doc: ExtractedDocument, li: LineItem) -> EvidenceItem:
    return EvidenceItem(
        document_id=doc.document_id,
        page=li.quantity.page,
        bbox=li.quantity.bbox,
        field="quantity",
        raw=li.quantity.raw,
    )


def _check_qty_against(
    ctx: CheckContext, check_id: str, ref_type: DocumentType, ref_label: str,
) -> CheckResult:
    if ctx.cluster is None:
        return CheckResult.skipped(
            check_id, "Cross-document check: no cluster context on this run",
        )
    refs = ctx.cluster.of_type(ref_type)
    if not refs:
        return CheckResult.skipped(check_id, f"No {ref_label} in cluster")

    ref_qty: dict[str, Decimal] = {}
    ref_line: dict[str, tuple[ExtractedDocument, LineItem]] = {}
    for ref in refs:
        for key, (li, qty) in _qty_by_desc(ref).items():
            ref_qty[key] = ref_qty.get(key, Decimal("0")) + qty
            ref_line[key] = (ref, li)

    for key, (li, qty) in _qty_by_desc(ctx.document).items():
        if key not in ref_qty:
            continue  # unmatched line: no verdict (precision-first)
        if qty > ref_qty[key]:
            ref_doc, ref_li = ref_line[key]
            return CheckResult.failed(
                check_id,
                expected=f"<= {ref_qty[key]}",
                actual=str(qty),
                delta=str(qty - ref_qty[key]),
                message=(
                    f"Line {li.line_number} ({li.description.value}): qty {qty} "
                    f"exceeds {ref_label} qty {ref_qty[key]}"
                ),
                evidence=[
                    _qty_evidence(ctx.document, li),
                    _qty_evidence(ref_doc, ref_li),
                ],
            )
    return CheckResult.passed(check_id)


def check_quantity_po(ctx: CheckContext) -> CheckResult:
    """CHK-REF-QTY-001 — invoiced/challan qty <= PO qty."""
    return _check_qty_against(
        ctx, "CHK-REF-QTY-001", DocumentType.PURCHASE_ORDER, "PO",
    )


def check_quantity_dc(ctx: CheckContext) -> CheckResult:
    """CHK-REF-QTY-002 — received qty <= delivery challan qty."""
    return _check_qty_against(
        ctx, "CHK-REF-QTY-002", DocumentType.DELIVERY_CHALLAN, "delivery challan",
    )
