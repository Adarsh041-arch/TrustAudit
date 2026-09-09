"""Conservative transaction checks with complete line coverage and cumulative quantities."""

from decimal import Decimal

from audit_v2.domain.models import (
    CheckContext,
    CheckResult,
    DocumentType,
    EvidenceItem,
    ExtractedDocument,
    FindingStatus,
    LineItem,
)


def _key(li: LineItem) -> str:
    value = li.po_line_reference or li.item_code or li.description
    return value.value.strip().casefold()


def _evidence(doc: ExtractedDocument, li: LineItem, field: str) -> EvidenceItem:
    pv = getattr(li, field)
    return EvidenceItem(
        document_id=doc.document_id,
        page=pv.page,
        bbox=pv.bbox,
        field=f"line_items[{li.line_number}].{field}",
        raw=pv.raw,
    )


def _finish(
    ctx: CheckContext, result: CheckResult, total: int, matched: int, issues: list[str]
) -> CheckResult:
    result.coverage = {
        "required_lines": total,
        "matched_lines": matched,
        "unmatched_lines": total - matched,
    }
    if result.status != FindingStatus.FAIL:
        reasons = list(issues)
        if ctx.cluster:
            reasons.extend(ctx.cluster.review_reasons)
            for doc in ctx.cluster.documents:
                if (
                    not doc.coverage.coverage_complete
                    or doc.grounding_rejections
                    or doc.extraction_disagreements
                ):
                    reasons.append(
                        f"Reference evidence for {doc.document_id} is incomplete or disputed"
                    )
        if not total:
            reasons.append("No invoice lines available for comparison")
        if reasons:
            result.status = (
                FindingStatus.NOT_RUN if issues or not total else FindingStatus.NEEDS_REVIEW
            )
            result.requires_human_review = True
            result.message = "; ".join(dict.fromkeys(reasons))
    return result


def compare_quantity(ctx: CheckContext, check_id: str, ref_type: DocumentType) -> CheckResult:
    if ctx.cluster is None:
        return CheckResult.unresolved(check_id, "No transaction cluster available")
    refs = ctx.cluster.of_type(ref_type)
    if not refs:
        return CheckResult.unresolved(check_id, f"Missing {ref_type.value} in transaction")
    if ref_type == DocumentType.PURCHASE_ORDER and len(refs) != 1:
        return CheckResult.unresolved(
            check_id, "Resolve competing PO versions before quantity checks"
        )
    # All invoices consume the same receipt/PO pool. A second invoice cannot reuse capacity.
    subjects = ctx.cluster.of_type(ctx.document.doc_type)
    available: dict[str, list[tuple[ExtractedDocument, LineItem]]] = {}
    demanded: dict[str, list[tuple[ExtractedDocument, LineItem]]] = {}
    for collection, docs in ((available, refs), (demanded, subjects)):
        for doc in docs:
            for li in doc.line_items:
                collection.setdefault(_key(li), []).append((doc, li))
    result = CheckResult.passed(check_id)
    issues: list[str] = []
    failures: list[str] = []
    matched = 0
    for key in sorted({_key(li) for li in ctx.document.line_items}):
        own_count = sum(_key(li) == key for li in ctx.document.line_items)
        supply, demand = available.get(key, []), demanded[key]
        if not supply:
            issues.append(f"Unmatched item: {key}")
            continue
        lines = supply + demand
        units = {
            li.quantity_unit.value.strip().casefold() if li.quantity_unit else "" for _, li in lines
        }
        if "" in units or len(units) != 1:
            issues.append(f"Unknown or incompatible units for {key}; no implicit conversion")
            continue
        quantities = [li.quantity.decimal_value for _, li in lines]
        if any(not q.is_finite() or q < 0 for q in quantities):
            issues.append(f"Unsupported return/negative quantity for {key}")
            continue
        received = sum((li.quantity.decimal_value for _, li in supply), Decimal(0))
        invoiced = sum((li.quantity.decimal_value for _, li in demand), Decimal(0))
        matched += own_count
        result.evidence.extend(_evidence(doc, li, "quantity") for doc, li in lines)
        if invoiced > received:
            if result.actual is None:
                result.expected, result.actual, result.delta = (
                    f"<= {received}",
                    str(invoiced),
                    str(invoiced - received),
                )
            failures.append(
                f"{key}: cumulative quantity {invoiced} exceeds {ref_type.value} "
                f"quantity {received}"
            )
    if failures:
        result.status = FindingStatus.FAIL
        result.message = "; ".join(failures)
        result.requires_human_review = True
    return _finish(ctx, result, len(ctx.document.line_items), matched, issues)


def check_invoiced_vs_received(ctx: CheckContext) -> CheckResult:
    return compare_quantity(ctx, "CHK-XDOC-QTY-001", DocumentType.GOODS_RECEIPT_NOTE)


def check_price_matches_po(ctx: CheckContext) -> CheckResult:
    check_id = "CHK-XDOC-PRICE-001"
    po = ctx.cluster.purchase_order if ctx.cluster else None
    if po is None:
        return CheckResult.unresolved(check_id, "A unique purchase order is required")
    result = CheckResult.passed(check_id)
    issues: list[str] = []
    failures: list[str] = []
    matched = 0
    for li in ctx.document.line_items:
        candidates = [p for p in po.line_items if _key(p) == _key(li)]
        if len(candidates) != 1:
            issues.append(f"Line {li.line_number}: missing or ambiguous PO line")
            continue
        ref = candidates[0]
        currency = li.unit_price.currency
        unit = li.quantity_unit.value.strip().casefold() if li.quantity_unit else None
        ref_unit = ref.quantity_unit.value.strip().casefold() if ref.quantity_unit else None
        if not currency or currency != ref.unit_price.currency or not unit or unit != ref_unit:
            issues.append(f"Line {li.line_number}: currency or unit is missing/incompatible")
            continue
        price, expected = li.unit_price.decimal_value, ref.unit_price.decimal_value
        if not price.is_finite() or not expected.is_finite() or min(price, expected) < 0:
            issues.append(f"Line {li.line_number}: unsupported price")
            continue
        matched += 1
        result.evidence.extend(
            [_evidence(ctx.document, li, "unit_price"), _evidence(po, ref, "unit_price")]
        )
        if abs(price - expected) > ctx.tolerance_for(check_id):
            if result.actual is None:
                result.expected, result.actual, result.delta = (
                    str(expected),
                    str(price),
                    str(abs(price - expected)),
                )
            failures.append(
                f"Line {li.line_number}: invoiced price {price} differs from PO price {expected}"
            )
    if failures:
        result.status = FindingStatus.FAIL
        result.message = "; ".join(failures)
        result.requires_human_review = True
    return _finish(ctx, result, len(ctx.document.line_items), matched, issues)


def check_receipt_exists(ctx: CheckContext) -> CheckResult:
    check_id = "CHK-XDOC-RECEIPT-001"
    if ctx.cluster is None:
        return CheckResult.unresolved(check_id, "No transaction context")
    if not ctx.cluster.of_type(DocumentType.GOODS_RECEIPT_NOTE):
        return CheckResult.unresolved(check_id, "Goods receipt evidence is missing")
    return _finish(ctx, CheckResult.passed(check_id), 1, 1, [])


def check_cumulative_invoiced(ctx: CheckContext) -> CheckResult:
    check_id = "CHK-XDOC-CUMUL-001"
    po = ctx.cluster.purchase_order if ctx.cluster else None
    if po is None or ctx.cluster is None:
        return CheckResult.unresolved(check_id, "A unique purchase order is required")
    docs = [po, *ctx.cluster.of_type(DocumentType.INVOICE)]
    # Only compare like-for-like totals. Never assume a PO grand total is pre-tax.
    field = "subtotal" if all(d.header.subtotal for d in docs) else "grand_total"
    values = [getattr(d.header, field) for d in docs]
    if any(v is None for v in values):
        return CheckResult.unresolved(check_id, f"Missing {field}; cannot compare cumulative value")
    currencies = {v.currency for v in values if v is not None}
    if None in currencies or len(currencies) != 1:
        return CheckResult.unresolved(
            check_id, "Cumulative comparison requires one explicit currency"
        )
    amounts = [v.decimal_value for v in values if v is not None]
    if any(not a.is_finite() or a < 0 for a in amounts):
        return CheckResult.unresolved(
            check_id, "Negative/non-finite totals require explicit adjustment handling"
        )
    cumulative = sum(amounts[1:], Decimal(0))
    result = CheckResult.passed(check_id)
    result.evidence = [
        EvidenceItem(document_id=d.document_id, page=v.page, bbox=v.bbox, field=field, raw=v.raw)
        for d, v in zip(docs, values, strict=True)
        if v
    ]
    if cumulative > amounts[0] + ctx.tolerance_for(check_id):
        result.status = FindingStatus.FAIL
        result.expected = str(amounts[0])
        result.actual = str(cumulative)
        result.delta = str(cumulative - amounts[0])
        result.message = f"Cumulative {field} {cumulative} exceeds PO {field} {amounts[0]}"
        result.requires_human_review = True
    return _finish(ctx, result, len(docs) - 1, len(docs) - 1, [])
