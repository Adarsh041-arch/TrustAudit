"""Safe evaluator for tenant-defined declarative checks."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from audit_v2.domain.models import (
    CheckContext,
    CheckResult,
    EvidenceItem,
    FindingStatus,
    ProvenancedValue,
)

ALLOWED_FIELDS = {
    "document.narrative_report",
    *{
        f"header.{name}"
        for name in (
            "vendor_name",
            "vendor_address",
            "vendor_gstin",
            "buyer_name",
            "buyer_gstin",
            "invoice_number",
            "po_number",
            "challan_number",
            "grn_number",
            "invoice_date",
            "due_date",
            "po_reference",
            "grand_total",
            "amount_in_words",
            "bank_details",
            "order_date",
            "delivery_date",
            "payment_terms",
            "delivery_address",
            "subtotal",
            "discount_amount",
            "discount_percentage",
            "expiry_date",
            "received_date",
            "grn_date",
            "certificate_number",
            "certificate_date",
            "exporter_name",
            "exporter_address",
            "consignee_name",
            "consignee_address",
            "country_of_origin",
            "referenced_invoice_number",
            "referenced_invoice_date",
            "issuing_authority",
            "signature_present",
            "seal_present",
        )
    },
    *{
        f"line_items.{name}"
        for name in (
            "description",
            "quantity",
            "unit_price",
            "line_total",
            "hsn_sac",
            "quantity_unit",
            "item_code",
            "po_line_reference",
        )
    },
    *{
        f"tax_lines.{name}"
        for name in (
            "description",
            "taxable_value",
            "rate",
            "cgst",
            "sgst",
            "total_tax",
        )
    },
    *{
        f"certificate_goods.{name}"
        for name in (
            "description",
            "hs_code",
            "quantity",
            "quantity_unit",
            "invoice_number",
            "invoice_date",
        )
    },
}


def _plain(value: Any) -> Any:
    if isinstance(value, ProvenancedValue):
        return value.value
    return value


def _values(ctx: CheckContext, path: str) -> list[Any]:
    root, field = path.split(".", 1)
    document = ctx.document
    if root == "header":
        return [_plain(getattr(document.header, field, None))]
    if root == "document":
        return [_plain(getattr(document, field, None))]
    rows = getattr(document, root, [])
    return [_plain(getattr(row, field, None)) for row in rows]


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value).replace(",", "").strip())
        if not result.is_finite():
            raise ValueError("Non-finite numeric value")
        return result
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"{value!r} is not numeric") from exc


def _matches(
    value: Any, operator: str, expected: str | None, second: str | None, case_sensitive: bool
) -> bool:
    present = value is not None and (not isinstance(value, str) or bool(value.strip()))
    if operator == "is_present":
        return present
    if not present:
        return False
    actual_text = str(value).strip()
    expected_text = (expected or "").strip()
    if not case_sensitive:
        actual_text, expected_text = actual_text.casefold(), expected_text.casefold()
    if operator == "equals":
        return actual_text == expected_text
    if operator == "not_equals":
        return actual_text != expected_text
    if operator == "contains":
        return expected_text in actual_text
    if operator == "starts_with":
        return actual_text.startswith(expected_text)
    if operator == "ends_with":
        return actual_text.endswith(expected_text)
    actual_number = _decimal(value)
    expected_number = _decimal(expected)
    if operator == "greater_than":
        return actual_number > expected_number
    if operator == "less_than":
        return actual_number < expected_number
    if operator == "between":
        return expected_number <= actual_number <= _decimal(second)
    raise ValueError(f"Unsupported custom rule operator: {operator}")


def evaluate_custom_rule(ctx: CheckContext) -> CheckResult:
    entry = ctx.check_entry
    definition = entry.custom_definition
    if definition is None:
        raise ValueError("Custom rule has no definition")
    if definition.field_path not in ALLOWED_FIELDS:
        return CheckResult(
            check_id=entry.check_id,
            status=FindingStatus.ERROR,
            message=f"Custom rule field is not supported: {definition.field_path}",
            requires_human_review=True,
        )
    values = _values(ctx, definition.field_path)
    matches = [
        _matches(
            value,
            definition.operator,
            definition.expected_value,
            definition.second_value,
            definition.case_sensitive,
        )
        for value in values
    ]
    passed = bool(matches) and (all(matches) if definition.quantifier == "all" else any(matches))
    if passed:
        return CheckResult.passed(entry.check_id)
    actual = ", ".join("missing" if value is None else str(value) for value in values[:10])
    expected = (
        "present"
        if definition.operator == "is_present"
        else definition.expected_value or "configured requirement"
    )
    result = CheckResult.failed(
        entry.check_id,
        expected=expected,
        actual=actual or "no matching values",
        delta="N/A",
        message=entry.failure_message,
    )
    root, field = definition.field_path.split(".", 1)
    containers = (
        [ctx.document.header]
        if root == "header"
        else ([ctx.document] if root == "document" else getattr(ctx.document, root, []))
    )
    result.evidence = [
        EvidenceItem(
            document_id=ctx.document.document_id,
            page=value.page,
            bbox=value.bbox,
            field=definition.field_path,
            raw=value.raw,
        )
        for container in containers
        if isinstance(value := getattr(container, field, None), ProvenancedValue)
    ][:50]
    result.coverage = {"required_values": len(values), "matched_values": sum(matches)}
    return result
