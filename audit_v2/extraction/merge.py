"""Dual-extraction merge — Phase 4 (PHASES_V2 §4).

Reconciles a regex-extracted document and a VLM-extracted document into one
merged document. Pure domain code: no network, no model calls.

Rules per field (header, line item, tax line):
- both sources agree  -> keep the regex value (sharper bbox/page provenance),
                         confidence boosted by the agreement
- both sources differ -> keep the regex value, penalize confidence, record a
                         disagreement (routes to human review upstream)
- one source only     -> keep it, penalized confidence (VLM-only or regex-only)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import overload

from audit_v2.domain.models import (
    Coverage,
    DocumentHeader,
    ExtractedDocument,
    LineItem,
    ProvenancedValue,
    TaxLine,
)
from audit_v2.extraction.confidence import compute_field_confidence
from audit_v2.extraction.parser import parse_amount, parse_date

MERGE_VERSION = "dual_1.0.0"

_MONEY_FIELDS = frozenset(
    {
        "subtotal",
        "grand_total",
        "discount_amount",
        "discount_percentage",
        "opening_balance",
        "receipts",
        "payments",
        "closing_balance",
    }
)
_DATE_FIELDS = frozenset(
    {
        "invoice_date",
        "due_date",
        "order_date",
        "delivery_date",
        "grn_date",
        "expiry_date",
        "received_date",
    }
)


@dataclass
class MergeResult:
    merged: ExtractedDocument
    disagreements: dict[str, str] = field(default_factory=dict)


def _normalized(pv: ProvenancedValue, field_name: str) -> str | date | Decimal:
    if field_name in _MONEY_FIELDS:
        parsed = parse_amount(pv.value)
        return parsed if parsed is not None else pv.value.strip().casefold()
    if field_name in _DATE_FIELDS:
        parsed_date = parse_date(pv.value)
        return parsed_date if parsed_date is not None else pv.value.strip().casefold()
    return pv.value.strip().casefold()


def _agree(pv_a: ProvenancedValue, pv_b: ProvenancedValue, field_name: str) -> bool:
    a, b = _normalized(pv_a, field_name), _normalized(pv_b, field_name)
    return a == b


@overload
def _merge_pv(
    field_name: str, regex_pv: ProvenancedValue, vlm_pv: ProvenancedValue
) -> tuple[ProvenancedValue, str | None]: ...


@overload
def _merge_pv(
    field_name: str, regex_pv: ProvenancedValue | None, vlm_pv: ProvenancedValue | None
) -> tuple[ProvenancedValue | None, str | None]: ...


def _merge_pv(
    field_name: str,
    regex_pv: ProvenancedValue | None,
    vlm_pv: ProvenancedValue | None,
) -> tuple[ProvenancedValue | None, str | None]:
    if regex_pv is None and vlm_pv is None:
        return None, None
    if regex_pv is None:
        return vlm_pv, None
    if vlm_pv is None:
        return regex_pv, None

    if _agree(regex_pv, vlm_pv, field_name):
        merged = regex_pv.model_copy(
            update={
                "confidence": compute_field_confidence(
                    field_name,
                    regex_pv.confidence,
                    vlm_pv.confidence,
                    1.0,
                ),
            }
        )
        return merged, None

    merged = regex_pv.model_copy(
        update={
            "confidence": compute_field_confidence(
                field_name,
                regex_pv.confidence,
                vlm_pv.confidence,
                0.0,
            ),
        }
    )
    return merged, f"{regex_pv.raw} vs {vlm_pv.raw}"


def _match_vlm_line(
    line: LineItem,
    vlm_lines: list[LineItem],
) -> LineItem | None:
    for candidate in vlm_lines:
        if candidate.line_number == line.line_number:
            return candidate
    desc = line.description.value.strip().casefold()
    for candidate in vlm_lines:
        if candidate.description.value.strip().casefold() == desc:
            return candidate
    return None


def _merge_line_items(
    regex_lines: list[LineItem],
    vlm_lines: list[LineItem],
    disagreements: dict[str, str],
) -> list[LineItem]:
    merged: list[LineItem] = []
    used: set[int] = set()
    for line in regex_lines:
        match = _match_vlm_line(line, vlm_lines)
        if match is None:
            merged.append(line)
            continue
        used.add(match.line_number)
        prefix = f"line_items[{line.line_number}]"
        desc, d = _merge_pv("description", line.description, match.description)
        if d:
            disagreements[f"{prefix}.description"] = d
        qty, d = _merge_pv("quantity", line.quantity, match.quantity)
        if d:
            disagreements[f"{prefix}.quantity"] = d
        price, d = _merge_pv("unit_price", line.unit_price, match.unit_price)
        if d:
            disagreements[f"{prefix}.unit_price"] = d
        total, d = _merge_pv("line_total", line.line_total, match.line_total)
        if d:
            disagreements[f"{prefix}.line_total"] = d
        hsn, d = _merge_pv("hsn_sac", line.hsn_sac, match.hsn_sac)
        if d:
            disagreements[f"{prefix}.hsn_sac"] = d
        quantity_unit, d = _merge_pv("quantity_unit", line.quantity_unit, match.quantity_unit)
        if d:
            disagreements[f"{prefix}.quantity_unit"] = d
        merged.append(
            LineItem(
                line_number=line.line_number,
                description=desc,
                quantity=qty,
                unit_price=price,
                line_total=total,
                hsn_sac=hsn,
                quantity_unit=quantity_unit,
            )
        )
    for line in vlm_lines:
        if line.line_number not in used:
            merged.append(line)
    return sorted(merged, key=lambda item: item.line_number)


def _merge_tax_lines(
    regex_lines: list[TaxLine],
    vlm_lines: list[TaxLine],
    disagreements: dict[str, str],
) -> list[TaxLine]:
    merged: list[TaxLine] = []
    used: set[int] = set()
    for line in regex_lines:
        match = next(
            (c for c in vlm_lines if c.line_number == line.line_number),
            None,
        )
        if match is None:
            merged.append(line)
            continue
        used.add(match.line_number)
        prefix = f"tax_lines[{line.line_number}]"
        fields = [
            ("description", line.description, match.description),
            ("taxable_value", line.taxable_value, match.taxable_value),
            ("rate", line.rate, match.rate),
            ("cgst", line.cgst, match.cgst),
            ("sgst", line.sgst, match.sgst),
            ("total_tax", line.total_tax, match.total_tax),
        ]
        values: dict[str, ProvenancedValue] = {}
        for name, a, b in fields:
            pv, d = _merge_pv(name, a, b)
            if d:
                disagreements[f"{prefix}.{name}"] = d
            values[name] = pv
        merged.append(
            TaxLine(
                line_number=line.line_number,
                description=values["description"],
                taxable_value=values["taxable_value"],
                rate=values["rate"],
                cgst=values["cgst"],
                sgst=values["sgst"],
                total_tax=values["total_tax"],
            )
        )
    for line in vlm_lines:
        if line.line_number not in used:
            merged.append(line)
    return sorted(merged, key=lambda item: item.line_number)


_HEADER_PV_FIELDS = (
    "vendor_name",
    "vendor_address",
    "vendor_gstin",
    "buyer_name",
    "buyer_gstin",
    "invoice_date",
    "due_date",
    "po_reference",
    "invoice_number",
    "po_number",
    "challan_number",
    "grn_number",
    "grand_total",
    "amount_in_words",
    "order_date",
    "delivery_date",
    "payment_terms",
    "delivery_address",
    "subtotal",
    "discount_amount",
    "discount_percentage",
    "opening_balance",
    "receipts",
    "payments",
    "closing_balance",
    "expiry_date",
    "received_date",
    "grn_date",
)


def _merge_headers(
    regex_header: DocumentHeader,
    vlm_header: DocumentHeader,
    disagreements: dict[str, str],
) -> DocumentHeader:
    merged = regex_header.model_copy(deep=True)
    for field_name in _HEADER_PV_FIELDS:
        pv, d = _merge_pv(
            field_name,
            getattr(regex_header, field_name),
            getattr(vlm_header, field_name),
        )
        if d:
            disagreements[field_name] = d
        setattr(merged, field_name, pv)
    if merged.bank_details is None:
        merged.bank_details = vlm_header.bank_details
    return merged


def _merge_coverage(a: Coverage, b: Coverage) -> Coverage:
    if a.coverage_complete:
        return a
    if b.coverage_complete:
        return b
    if b.pages_examined > a.pages_examined:
        return b
    return a


def merge_extractions(
    regex_doc: ExtractedDocument,
    vlm_doc: ExtractedDocument,
) -> MergeResult:
    """Merge a regex-extracted document and a VLM-extracted document.

    `regex_doc` is the deterministic side: on disagreement its value and
    provenance win, and the conflict is recorded for human review.
    """
    disagreements: dict[str, str] = {}
    header = _merge_headers(regex_doc.header, vlm_doc.header, disagreements)
    line_items = _merge_line_items(regex_doc.line_items, vlm_doc.line_items, disagreements)
    tax_lines = _merge_tax_lines(regex_doc.tax_lines, vlm_doc.tax_lines, disagreements)

    merged = ExtractedDocument(
        document_id=regex_doc.document_id,
        tenant_id=regex_doc.tenant_id,
        doc_type=regex_doc.doc_type,
        header=header,
        line_items=line_items,
        tax_lines=tax_lines,
        coverage=_merge_coverage(regex_doc.coverage, vlm_doc.coverage),
        page_count=max(regex_doc.page_count, vlm_doc.page_count),
        extractor_version=MERGE_VERSION,
        model_version=vlm_doc.model_version,
        grounding_rejections=list(vlm_doc.grounding_rejections),
        narrative_report=vlm_doc.narrative_report,
        extraction_disagreements=dict(disagreements),
        extraction_strategy=vlm_doc.extraction_strategy,
        vision_backend=vlm_doc.vision_backend,
        vision_call_count=vlm_doc.vision_call_count,
        glm_call_count=vlm_doc.glm_call_count,
        structured_fallback_used=vlm_doc.structured_fallback_used,
        transcript_cache_hit=vlm_doc.transcript_cache_hit,
        extraction_latency_ms=vlm_doc.extraction_latency_ms,
        fallback_reasons=list(vlm_doc.fallback_reasons),
    )
    return MergeResult(merged=merged, disagreements=disagreements)
