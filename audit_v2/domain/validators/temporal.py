"""Temporal validators — CHK-TEMP-* checks."""
from datetime import date, datetime

from audit_v2.domain.models import CheckContext, CheckResult, ProvenancedValue


def _parse_date(pv: ProvenancedValue | None) -> date | None:

    if pv is None or pv.value in (None, ""):
        return None
    raw = pv.value.strip()
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def check_invoice_date(ctx: CheckContext) -> CheckResult:
    """CHK-TEMP-INVDATE-001 — invoice date is not after received date."""
    doc = ctx.document
    inv_date = _parse_date(doc.header.invoice_date)
    recv_date = _parse_date(doc.header.received_date)
    if inv_date is None:
        return CheckResult.skipped("CHK-TEMP-INVDATE-001", "No invoice_date")
    if recv_date is None:
        return CheckResult.skipped("CHK-TEMP-INVDATE-001", "No received_date")
    if inv_date > recv_date:
        return CheckResult.failed(
            "CHK-TEMP-INVDATE-001",
            expected=str(recv_date),
            actual=str(inv_date),
            delta=str((inv_date - recv_date).days),
            message=f"Invoice date {inv_date} is after received date {recv_date}",
        )
    return CheckResult.passed("CHK-TEMP-INVDATE-001")


def check_po_date(ctx: CheckContext) -> CheckResult:
    """CHK-TEMP-PODATE-001 — PO date (order_date) is not after invoice date."""
    doc = ctx.document
    po_date = _parse_date(doc.header.order_date)
    inv_date = _parse_date(doc.header.invoice_date)
    if po_date is None:
        return CheckResult.skipped("CHK-TEMP-PODATE-001", "No order_date (PO date)")
    if inv_date is None:
        return CheckResult.skipped("CHK-TEMP-PODATE-001", "No invoice_date")
    if po_date > inv_date:
        return CheckResult.failed(
            "CHK-TEMP-PODATE-001",
            expected=str(po_date),
            actual=str(inv_date),
            delta=str((po_date - inv_date).days),
            message=f"PO date {po_date} is after invoice date {inv_date}",
        )
    return CheckResult.passed("CHK-TEMP-PODATE-001")


def check_delivery_date(ctx: CheckContext) -> CheckResult:
    """CHK-TEMP-DELIVERY-001 — delivery date is not after GRN date."""
    doc = ctx.document
    del_date = _parse_date(doc.header.delivery_date)
    grn_date = _parse_date(doc.header.grn_date)
    if del_date is None:
        return CheckResult.skipped("CHK-TEMP-DELIVERY-001", "No delivery_date")
    if grn_date is None:
        return CheckResult.skipped("CHK-TEMP-DELIVERY-001", "No grn_date")
    if del_date > grn_date:
        return CheckResult.failed(
            "CHK-TEMP-DELIVERY-001",
            expected=str(grn_date),
            actual=str(del_date),
            delta=str((del_date - grn_date).days),
            message=f"Delivery date {del_date} is after GRN date {grn_date}",
        )
    return CheckResult.passed("CHK-TEMP-DELIVERY-001")


def check_expiry_date(ctx: CheckContext) -> CheckResult:
    """CHK-TEMP-EXPIRY-001 — document has not passed its expiry date."""
    doc = ctx.document
    expiry = _parse_date(doc.header.expiry_date)
    if expiry is None:
        return CheckResult.skipped("CHK-TEMP-EXPIRY-001", "No expiry_date")
    today = date.today()
    if expiry < today:
        return CheckResult.failed(
            "CHK-TEMP-EXPIRY-001",
            expected=f">= {today}",
            actual=str(expiry),
            delta=str((today - expiry).days),
            message=f"Document expired on {expiry}",
        )
    return CheckResult.passed("CHK-TEMP-EXPIRY-001")
