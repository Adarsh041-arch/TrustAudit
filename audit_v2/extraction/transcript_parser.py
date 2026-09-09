"""Deterministic, label-anchored parsing of GLM-OCR page transcriptions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import BaseModel

from audit_v2.domain.models import DocumentType
from audit_v2.extraction.parser import parse_amount, parse_date
from audit_v2.extraction.schemas import (
    ContractExtraction,
    DeliveryChallanExtraction,
    GoodsReceiptExtraction,
    InvoiceExtraction,
    LetterExtraction,
    LineItemSchema,
    PurchaseOrderExtraction,
)

SUPPORTED_TYPES = frozenset(
    {
        DocumentType.INVOICE,
        DocumentType.PURCHASE_ORDER,
        DocumentType.DELIVERY_CHALLAN,
        DocumentType.GOODS_RECEIPT_NOTE,
        DocumentType.CONTRACT,
        DocumentType.LETTER,
    }
)

_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\dZ[A-Z0-9]\b", re.I)
_CURRENCY = re.compile(r"\b(USD|INR|EUR|GBP)\b|([$₹€£])", re.I)
_CURRENCY_MAP = {"$": "USD", "₹": "INR", "€": "EUR", "£": "GBP"}
_BUSINESS = re.compile(
    r"\b(?:Pvt\.?\s*Ltd\.?|Private\s+Limited|Ltd\.?|LLC|L\.L\.C\.?|Inc\.?|"
    r"Corporation|Corp\.?|Company|Co\.?)\b",
    re.I,
)
_TABLE_MARKERS = re.compile(
    r"\b(?:description|item|product)\b.*\b(?:qty|quantity)\b.*"
    r"\b(?:amount|total|value)\b",
    re.I,
)


@dataclass
class TranscriptParseResult:
    instance: BaseModel
    missing_fields: list[str] = field(default_factory=list)
    fallback_reasons: list[str] = field(default_factory=list)
    table_visible: bool = False

    @property
    def complete(self) -> bool:
        return not self.fallback_reasons


def _lines(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", line.strip().strip("| ")).strip()
        for line in text.splitlines()
        if line.strip().strip("| ")
    ]


def _label(text: str, labels: str) -> str | None:
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("| ")
        match = re.match(
            rf"(?i)^(?:{labels})\s*(?:No\.?|Number)?\s*"
            rf"(?:[:#|\t-]\s*)+([^|\t]+)",
            line,
        )
        if match:
            return match.group(1).strip()
    return None


def _date_value(text: str, labels: str) -> str | None:
    raw = _label(text, labels)
    if raw is None:
        return None
    parsed = parse_date(raw)
    return parsed.isoformat() if parsed else raw.strip()


def _currency(text: str) -> str | None:
    match = _CURRENCY.search(text)
    if not match:
        return None
    token = (match.group(1) or match.group(2)).upper()
    return _CURRENCY_MAP.get(token, token)


def _section_name(text: str, label: str) -> str | None:
    lines = _lines(text)
    for idx, line in enumerate(lines):
        match = re.match(rf"(?i)^{label}\s*:?[ ]*(.*)$", line)
        if not match:
            continue
        inline = match.group(1).strip("| ")
        if inline and not re.match(r"(?i)^(address|p\.?o\.? box|gst|vat)\b", inline):
            return inline
        for candidate in lines[idx + 1 : idx + 4]:
            if _BUSINESS.search(candidate):
                return candidate
            if re.match(r"(?i)^(address|p\.?o\.? box|gst|vat|buyer|consignee)\b", candidate):
                break
    return None


def _masthead_vendor(text: str) -> str | None:
    lines = _lines(text)
    for line in lines[:8]:
        if re.search(r"(?i)\b(?:invoice|purchase order|delivery challan|goods receipt)\b", line):
            continue
        if _BUSINESS.search(line):
            return line
    return None


def _context_gstins(text: str) -> tuple[str | None, str | None]:
    upper = text.upper()
    buyer_at = min(
        (pos for token in ("BUYER", "BILL TO", "CONSIGNEE") if (pos := upper.find(token)) >= 0),
        default=-1,
    )
    vendor: str | None = None
    buyer: str | None = None
    for match in _GSTIN.finditer(upper):
        if buyer_at >= 0 and match.start() > buyer_at:
            buyer = buyer or match.group(0)
        else:
            vendor = vendor or match.group(0)
    return vendor, buyer


def _explicit_total(text: str) -> tuple[str | None, bool]:
    pattern = re.compile(
        r"(?im)^\s*\|?\s*(?:grand\s+total|invoice\s+total|total\s+invoice\s+value"
        r"(?:\s*\([^)]*\))?|amount\s+payable|net\s+amount|total\s+amount)"
        r"(?:\s*[:|-]\s*)*(?:USD|INR|EUR|GBP|[$₹€£])?\s*"
        r"([0-9][0-9,]*(?:\.\d{1,2})?)\s*\|?\s*$"
    )
    values: list[Decimal] = []
    raws: list[str] = []
    for match in pattern.finditer(text):
        parsed = parse_amount(match.group(1))
        if parsed is not None:
            values.append(parsed)
            raws.append(match.group(1))
    unique = set(values)
    if len(unique) > 1:
        return None, True
    return (str(values[-1]) if values else None), False


def _header_index(headers: list[str], aliases: tuple[str, ...]) -> int | None:
    for idx, header in enumerate(headers):
        normalized = re.sub(r"[^a-z0-9]+", " ", header.casefold()).strip()
        if any(alias in normalized for alias in aliases):
            return idx
    return None


def _pipe_items(text: str, *, require_prices: bool = True) -> list[LineItemSchema]:
    source_lines = text.splitlines()
    row_entries = [
        (line_number, [cell.strip() for cell in line.strip().strip("|").split("|")])
        for line_number, line in enumerate(source_lines)
        if line.count("|") >= 3
    ]
    rows = [cells for _, cells in row_entries]
    for row_idx, headers in enumerate(rows):
        desc_i = _header_index(headers, ("description", "item", "product"))
        qty_i = _header_index(headers, ("quantity", "qty"))
        price_i = _header_index(headers, ("unit price", "rate", "price"))
        total_i = _header_index(headers, ("amount", "line total", "value"))
        hsn_i = _header_index(headers, ("hs code", "hsn", "sac"))
        required_indexes = (desc_i, qty_i, price_i, total_i) if require_prices else (desc_i, qty_i)
        if desc_i is None or qty_i is None or any(index is None for index in required_indexes):
            continue
        items: list[LineItemSchema] = []
        for entry_idx, cells in enumerate(rows[row_idx + 1 :], start=row_idx + 1):
            present_indexes = [
                index for index in (desc_i, qty_i, price_i, total_i) if index is not None
            ]
            if len(cells) <= max(present_indexes):
                continue
            if all(re.fullmatch(r":?-{2,}:?", cell.replace(" ", "")) for cell in cells):
                continue
            if re.search(r"(?i)\b(?:grand total|total invoice|subtotal)\b", cells[desc_i]):
                break
            quantity = cells[qty_i]
            quantity_match = re.search(r"[0-9][0-9,.]*", quantity)
            unit_match = re.search(r"(?i)\b([A-Z]{1,5})\b", quantity)
            description = cells[desc_i]
            next_row_line = (
                row_entries[entry_idx + 1][0]
                if entry_idx + 1 < len(row_entries)
                else len(source_lines)
            )
            continuations: list[str] = []
            for line in source_lines[row_entries[entry_idx][0] + 1 : next_row_line]:
                candidate = line.strip()
                if not candidate:
                    continue
                if re.match(
                    r"(?i)^(?:total|subtotal|tax|amount\s+in\s+words|for\s+|"
                    r"authorized|signature)",
                    candidate,
                ):
                    break
                continuations.append(candidate)
            if continuations:
                description = " ".join([description, *continuations]).strip()
            item = LineItemSchema(
                description=description or None,
                quantity=quantity_match.group(0) if quantity_match else None,
                unit_price=(cells[price_i] or None) if price_i is not None else None,
                line_total=(cells[total_i] or None) if total_i is not None else None,
                hsn_sac=cells[hsn_i] if hsn_i is not None and hsn_i < len(cells) else None,
                quantity_unit=unit_match.group(1).upper() if unit_match else None,
            )
            required_values = (
                (item.description, item.quantity, item.unit_price, item.line_total)
                if require_prices
                else (item.description, item.quantity)
            )
            if all(required_values):
                items.append(item)
        return items
    return []


def _whitespace_items(text: str) -> list[LineItemSchema]:
    items: list[LineItemSchema] = []
    for line in text.splitlines():
        if not line.strip() or _TABLE_MARKERS.search(line):
            continue
        match = re.match(
            r"^\s*(?P<desc>[A-Za-z][A-Za-z0-9 /&().%-]*?)\s{2,}"
            r"(?:(?P<hsn>\d{4,8})\s{2,})?"
            r"(?P<qty>\d[\d,.]*)(?:\s+[A-Za-z]{1,5})?\s{2,}"
            r"(?P<price>\d[\d,.]*)\s{2,}(?P<total>\d[\d,.]*)\s*$",
            line,
        )
        if match:
            items.append(
                LineItemSchema(
                    description=match.group("desc").strip(),
                    quantity=match.group("qty"),
                    unit_price=match.group("price"),
                    line_total=match.group("total"),
                    hsn_sac=match.group("hsn"),
                )
            )
    return items


def _vertical_items(text: str) -> list[LineItemSchema]:
    """Parse GLM's common one-column rendering of a visual table."""
    lines = _lines(text)

    def indexes(pattern: str) -> list[int]:
        return [idx for idx, line in enumerate(lines) if re.fullmatch(pattern, line, re.I)]

    desc_indexes = indexes(r"description(?:\s+of\s+goods)?")
    hsn_indexes = indexes(r"(?:hs|hsn|sac)\s*code")
    qty_indexes = indexes(r"(?:qty|quantity)")
    price_indexes = indexes(r"(?:unit\s+price|rate)(?:\s*\([^)]*\))?")
    amount_indexes = indexes(r"amount(?:\s*\([^)]*\))?")
    if not all((desc_indexes, hsn_indexes, qty_indexes, price_indexes, amount_indexes)):
        return []

    hsn_idx = next(
        (
            idx
            for idx in reversed(hsn_indexes)
            if idx + 1 < len(lines) and re.fullmatch(r"\d{4,8}", lines[idx + 1])
        ),
        -1,
    )
    qty_idx, price_idx, amount_idx = qty_indexes[0], price_indexes[0], amount_indexes[0]
    if hsn_idx < 0 or not (hsn_idx < qty_idx < price_idx < amount_idx):
        return []
    if any(idx + 1 >= len(lines) for idx in (hsn_idx, qty_idx, price_idx, amount_idx)):
        return []

    description_parts = [
        line
        for line in lines[desc_indexes[0] + 1 : hsn_idx]
        if not re.fullmatch(r"(?:hs|hsn|sac)\s*code", line, re.I)
    ]
    quantity_raw = lines[qty_idx + 1]
    quantity_match = re.search(r"[0-9][0-9,.]*", quantity_raw)
    unit_match = re.search(r"(?i)\b([A-Z]{1,5})\b", quantity_raw)
    if not description_parts or not quantity_match:
        return []
    return [
        LineItemSchema(
            description=" ".join(description_parts),
            hsn_sac=lines[hsn_idx + 1],
            quantity=quantity_match.group(0),
            quantity_unit=unit_match.group(1).upper() if unit_match else None,
            unit_price=lines[price_idx + 1],
            line_total=lines[amount_idx + 1],
        )
    ]


def _items(text: str, *, require_prices: bool = True) -> tuple[list[LineItemSchema], bool]:
    visible = bool(_TABLE_MARKERS.search(text)) or all(
        re.search(pattern, text, re.I)
        for pattern in (
            (r"description(?:\s+of\s+goods)?", r"\b(?:qty|quantity)\b", r"\bamount\b")
            if require_prices
            else (r"description(?:\s+of\s+goods)?|\bitem\b", r"\b(?:qty|quantity)\b")
        )
    )
    if require_prices:
        items = _pipe_items(text) or _whitespace_items(text) or _vertical_items(text)
    else:
        items = _pipe_items(text, require_prices=False)
    return items, visible


def _common(text: str, *, require_prices: bool = True) -> dict[str, object]:
    vendor_gstin, buyer_gstin = _context_gstins(text)
    items, table_visible = _items(text, require_prices=require_prices)
    return {
        "vendor_name": _section_name(text, r"(?:seller|vendor|supplier)") or _masthead_vendor(text),
        "vendor_gstin": vendor_gstin,
        "buyer_name": _section_name(text, r"(?:buyer|bill\s+to|customer|consignee)"),
        "buyer_gstin": buyer_gstin,
        "currency": _currency(text),
        "line_items": items,
        "table_visible": table_visible,
    }


def _contract_parties(text: str) -> tuple[str | None, str | None]:
    """Read explicitly delimited BETWEEN/AND contract parties."""
    lines = _lines(text)

    def after(marker: str) -> str | None:
        marker_index = next(
            (idx for idx, line in enumerate(lines) if re.fullmatch(marker, line, re.I)),
            None,
        )
        if marker_index is None:
            return None
        for candidate in lines[marker_index + 1 : marker_index + 7]:
            if _BUSINESS.search(candidate):
                return candidate.rstrip(",")
        return None

    return (
        after(r"BETWEEN") or _section_name(text, r"(?:seller|party\s+a)"),
        after(r"AND") or _section_name(text, r"(?:buyer|party\s+b)"),
    )


def _contract_effective_date(text: str) -> str | None:
    labelled = _date_value(text, r"(?:effective\s+date|contract\s+date|date)")
    if labelled:
        return labelled
    match = re.search(
        r"(?i)\b(?:contract|agreement)\s+is\s+(?:made|entered\s+into|executed)\s+"
        r"(?:on|as\s+of)\s+([^\r\n]+)",
        text,
    )
    if not match:
        return None
    raw = match.group(1).strip().rstrip(".,")
    parsed = parse_date(raw)
    return parsed.isoformat() if parsed else raw


def _contract_expiry_date(text: str) -> str | None:
    """Return an expiry only when an expiry/validity label is explicit."""
    match = re.search(
        r"(?im)^\s*(?:expiry\s+date|expiration\s+date|expires\s+on|valid\s+until|"
        r"valid\s+through)\s*[:#-]?\s*([^\r\n]+)",
        text,
    )
    if not match:
        return None
    raw = match.group(1).strip().rstrip(".,")
    parsed = parse_date(raw)
    return parsed.isoformat() if parsed else raw


def parse_transcript(
    doc_type: DocumentType, text: str, *, first_page: bool
) -> TranscriptParseResult:
    """Parse one OCR page without calculating or inventing absent values."""
    instance: BaseModel
    required: tuple[str, ...]
    if doc_type not in SUPPORTED_TYPES:
        raise ValueError(f"No deterministic transcript parser for {doc_type.value}")
    if doc_type == DocumentType.LETTER:
        instance = LetterExtraction(
            sender=_section_name(text, r"(?:from|sender)"),
            recipient=_section_name(text, r"(?:to|recipient)"),
            date=_date_value(text, r"(?:letter\s+date|date|dated)"),
            reference=_label(text, r"(?:letter|reference|ref)"),
            subject=_label(text, r"(?:subject|re)"),
        )
        required = ("sender", "date")
        missing = [name for name in required if first_page and not getattr(instance, name)]
        return TranscriptParseResult(
            instance=instance,
            missing_fields=missing,
            fallback_reasons=[f"missing:{name}" for name in missing],
        )
    if doc_type == DocumentType.CONTRACT:
        party_a, party_b = _contract_parties(text)
        instance = ContractExtraction(
            party_a=party_a,
            party_b=party_b,
            effective_date=_contract_effective_date(text),
            expiry_date=_contract_expiry_date(text),
            reference=_label(text, r"(?:(?:proforma|performa)\s+invoice|contract|agreement)"),
            subject=next(iter(_lines(text)), None),
        )
        required = ("party_a", "party_b", "effective_date", "reference")
        missing = [name for name in required if first_page and not getattr(instance, name, None)]
        return TranscriptParseResult(
            instance=instance,
            missing_fields=missing,
            fallback_reasons=[f"missing:{name}" for name in missing],
            table_visible=False,
        )

    common = _common(
        text,
        require_prices=doc_type
        not in {
            DocumentType.DELIVERY_CHALLAN,
            DocumentType.GOODS_RECEIPT_NOTE,
        },
    )
    table_visible = bool(common.pop("table_visible"))
    total, ambiguous_total = _explicit_total(text)

    if doc_type == DocumentType.INVOICE:
        instance = InvoiceExtraction.model_validate(
            dict(
                **common,
                invoice_number=_label(text, r"(?:(?:proforma\s+)?invoice|inv)"),
                invoice_date=_date_value(text, r"(?:invoice\s+date|date|dated)"),
                po_reference=_label(text, r"(?:PO|P\.O\.|purchase\s+order)"),
                grand_total=total,
                amount_in_words=_label(text, r"(?:amount\s+in\s+words|in\s+words)"),
            )
        )
        required = ("vendor_name", "invoice_number", "invoice_date", "grand_total")
    elif doc_type == DocumentType.PURCHASE_ORDER:
        instance = PurchaseOrderExtraction.model_validate(
            dict(
                **{k: v for k, v in common.items() if k != "buyer_gstin"},
                po_number=_label(text, r"(?:PO|P\.O\.|purchase\s+order)"),
                order_date=_date_value(text, r"(?:order\s+date|date|dated)"),
                grand_total=total,
            )
        )
        required = ("vendor_name", "po_number", "order_date")
    elif doc_type == DocumentType.DELIVERY_CHALLAN:
        simple_common = {
            k: v for k, v in common.items() if k not in {"vendor_gstin", "buyer_gstin", "currency"}
        }
        instance = DeliveryChallanExtraction.model_validate(
            dict(
                **simple_common,
                challan_number=_label(text, r"(?:challan|DC)"),
                delivery_date=_date_value(text, r"(?:delivery\s+date|date|dated)"),
                po_reference=_label(text, r"(?:PO|P\.O\.|purchase\s+order)"),
            )
        )
        required = ("vendor_name", "challan_number", "delivery_date")
    else:
        simple_common = {
            k: v for k, v in common.items() if k not in {"vendor_gstin", "buyer_gstin", "currency"}
        }
        instance = GoodsReceiptExtraction.model_validate(
            dict(
                **simple_common,
                grn_number=_label(text, r"(?:GRN|goods\s+receipt\s+note)"),
                grn_date=_date_value(text, r"(?:GRN\s+date|receipt\s+date|date|dated)"),
                po_reference=_label(text, r"(?:PO|P\.O\.|purchase\s+order)"),
            )
        )
        required = ("vendor_name", "grn_number", "grn_date")

    missing = [name for name in required if first_page and not getattr(instance, name, None)]
    reasons = [f"missing:{name}" for name in missing]
    if table_visible and not getattr(instance, "line_items", []):
        reasons.append("visible_table_unparsed")
    if ambiguous_total:
        reasons.append("ambiguous:grand_total")
    return TranscriptParseResult(instance, missing, reasons, table_visible)
