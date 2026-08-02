"""Cross-document (three-way match) validators — CHK-XDOC-* checks.

Phase 7 (PHASES_V2 §4). Pure functions over a TransactionCluster carried on
the CheckContext. When no cluster context is present (single-document run)
they SKIP with an explicit reason — an unrunnable check never reports PASS.

The subject document is ctx.document (an invoice); reference documents
(PO, GRN) come from ctx.cluster. Lines are matched across documents by
normalized description; unmatched lines produce no verdict (precision-first).
"""
from decimal import Decimal

from audit_v2.domain.models import (
    CheckContext,
    CheckResult,
    DocumentType,
    EvidenceItem,
    ExtractedDocument,
    LineItem,
)

NO_CLUSTER = "Cross-document check: no cluster context on this run"


def _norm(s: str) -> str:
    return s.strip().casefold()


def _lines_by_desc(doc: ExtractedDocument) -> dict[str, LineItem]:
    return {_norm(li.description.value): li for li in doc.line_items}


def _evidence(doc: ExtractedDocument, li: LineItem, field: str) -> EvidenceItem:
    pv = getattr(li, field)
    return EvidenceItem(
        document_id=doc.document_id,
        page=pv.page,
        bbox=pv.bbox,
        field=field,
        raw=pv.raw,
    )


def check_invoiced_vs_received(ctx: CheckContext) -> CheckResult:
    """CHK-XDOC-QTY-001 — invoiced quantity <= received quantity (GRN)."""
    check_id = "CHK-XDOC-QTY-001"
    if ctx.cluster is None:
        return CheckResult.skipped(check_id, NO_CLUSTER)
    grns = ctx.cluster.of_type(DocumentType.GOODS_RECEIPT_NOTE)
    if not grns:
        return CheckResult.skipped(check_id, "No goods receipt in cluster")

    # Aggregate received quantity per item description across all GRNs.
    received: dict[str, Decimal] = {}
    grn_lines: dict[str, tuple[ExtractedDocument, LineItem]] = {}
    for grn in grns:
        for li in grn.line_items:
            key = _norm(li.description.value)
            received[key] = received.get(key, Decimal("0")) + li.quantity.decimal_value
            grn_lines[key] = (grn, li)

    for li in ctx.document.line_items:
        key = _norm(li.description.value)
        if key not in received:
            continue  # unmatched line: no verdict
        invoiced = li.quantity.decimal_value
        if invoiced > received[key]:
            grn, grn_li = grn_lines[key]
            return CheckResult.failed(
                check_id,
                expected=f"<= {received[key]}",
                actual=str(invoiced),
                delta=str(invoiced - received[key]),
                message=(
                    f"Line {li.line_number} ({li.description.value}): invoiced qty "
                    f"{invoiced} > received qty {received[key]}"
                ),
                evidence=[
                    _evidence(ctx.document, li, "quantity"),
                    _evidence(grn, grn_li, "quantity"),
                ],
            )
    return CheckResult.passed(check_id)


def check_price_matches_po(ctx: CheckContext) -> CheckResult:
    """CHK-XDOC-PRICE-001 — invoiced unit price matches PO price within tolerance."""
    check_id = "CHK-XDOC-PRICE-001"
    if ctx.cluster is None:
        return CheckResult.skipped(check_id, NO_CLUSTER)
    po = ctx.cluster.purchase_order
    if po is None:
        return CheckResult.skipped(check_id, "No purchase order in cluster")

    po_lines = _lines_by_desc(po)
    tolerance = ctx.tolerance_for(check_id)
    for li in ctx.document.line_items:
        po_li = po_lines.get(_norm(li.description.value))
        if po_li is None:
            continue  # unmatched line: no verdict
        inv_price = li.unit_price.decimal_value
        po_price = po_li.unit_price.decimal_value
        delta = abs(inv_price - po_price)
        if delta > tolerance:
            return CheckResult.failed(
                check_id,
                expected=str(po_price),
                actual=str(inv_price),
                delta=str(delta),
                message=(
                    f"Line {li.line_number} ({li.description.value}): invoiced price "
                    f"{inv_price} != PO price {po_price}"
                ),
                evidence=[
                    _evidence(ctx.document, li, "unit_price"),
                    _evidence(po, po_li, "unit_price"),
                ],
            )
    return CheckResult.passed(check_id)


def check_receipt_exists(ctx: CheckContext) -> CheckResult:
    """CHK-XDOC-RECEIPT-001 — invoice above value threshold has a goods receipt."""
    check_id = "CHK-XDOC-RECEIPT-001"
    if ctx.cluster is None:
        return CheckResult.skipped(check_id, NO_CLUSTER)
    total = ctx.document.header.grand_total
    if total is None:
        return CheckResult.skipped(check_id, "No grand total on invoice")

    threshold = ctx.tolerance_for(check_id)
    amount = total.decimal_value
    if amount <= threshold:
        return CheckResult.passed(
            check_id, message=f"{check_id}: below receipt threshold {threshold}",
        )
    if ctx.cluster.of_type(DocumentType.GOODS_RECEIPT_NOTE):
        return CheckResult.passed(check_id)
    return CheckResult.failed(
        check_id,
        expected="goods receipt in cluster",
        actual="none",
        delta="N/A",
        message=(
            f"Invoice total {amount} exceeds receipt threshold {threshold} "
            f"with no goods receipt in cluster {ctx.cluster.cluster_id}"
        ),
        evidence=[EvidenceItem(
            document_id=ctx.document.document_id,
            page=total.page,
            bbox=total.bbox,
            field="grand_total",
            raw=total.raw,
        )],
        requires_human_review=True,
    )


def check_cumulative_invoiced(ctx: CheckContext) -> CheckResult:
    """CHK-XDOC-CUMUL-001 — cumulative invoiced across the cluster <= PO value.

    The highest-value fraud check in the system: over-billing spread across
    multiple invoices is invisible to any single-document audit.
    """
    check_id = "CHK-XDOC-CUMUL-001"
    if ctx.cluster is None:
        return CheckResult.skipped(check_id, NO_CLUSTER)
    po = ctx.cluster.purchase_order
    if po is None or po.header.grand_total is None:
        return CheckResult.skipped(check_id, "No purchase order value in cluster")

    invoices = ctx.cluster.of_type(DocumentType.INVOICE)
    totals: list[tuple[ExtractedDocument, Decimal]] = []
    for inv in invoices:
        if inv.header.grand_total is None:
            return CheckResult.skipped(
                check_id, f"Invoice {inv.document_id} has no grand total",
            )
        totals.append((inv, inv.header.grand_total.decimal_value))

    # Invoices carry GST on top of the PO's pre-tax order value; compare the
    # invoiced taxable value (subtotal) where present, else the grand total.
    cumulative = Decimal("0")
    for inv, total in totals:
        if inv.header.subtotal is not None:
            cumulative += inv.header.subtotal.decimal_value
        else:
            cumulative += total

    po_value = po.header.grand_total.decimal_value
    if cumulative > po_value + ctx.tolerance_for(check_id):
        gt = po.header.grand_total
        return CheckResult.failed(
            check_id,
            expected=f"<= {po_value}",
            actual=str(cumulative),
            delta=str(cumulative - po_value),
            message=(
                f"Cluster {ctx.cluster.cluster_id}: cumulative invoiced {cumulative} "
                f"exceeds PO value {po_value} across {len(invoices)} invoice(s)"
            ),
            evidence=[EvidenceItem(
                document_id=po.document_id,
                page=gt.page,
                bbox=gt.bbox,
                field="grand_total",
                raw=gt.raw,
            )],
            requires_human_review=True,
        )
    return CheckResult.passed(check_id)
