"""Ground structured model output in a page's raw OCR transcription."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from audit_v2.extraction.parser import parse_amount

_NUMERIC_FIELDS = {
    "subtotal",
    "discount_amount",
    "grand_total",
    "value_amount",
    "quantity",
    "unit_price",
    "line_total",
    "taxable_value",
    "rate",
    "cgst",
    "sgst",
    "total_tax",
}
_DATE_FIELDS = {
    "invoice_date",
    "due_date",
    "order_date",
    "delivery_date",
    "grn_date",
    "received_date",
    "effective_date",
    "expiry_date",
    "date",
    "certificate_date",
    "referenced_invoice_date",
}
_ADVISORY_FIELDS = {
    "narrative_report",
    "other_necessary_details",
    "signature_present",
    "seal_present",
}
_MONEY_TOKEN = re.compile(
    r"(?<![\w-])(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)?\s*"
    # Do not treat whitespace-separated table columns as digit grouping. That
    # would turn ``2 100.00`` into 2100 and make valid line items ungroundable.
    r"(\d+(?:,\d{2,3})*(?:\.\d+)?)(?![\w-])",
    re.IGNORECASE,
)


@dataclass
class GroundingIssue:
    field: str
    candidate: str
    page: int
    reason: str = "value is not supported by raw OCR transcription"

    def message(self) -> str:
        return f"page {self.page} {self.field}: {self.candidate!r} ({self.reason})"


@dataclass
class GroundingResult:
    instance: BaseModel
    issues: list[GroundingIssue] = field(default_factory=list)


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(ch for ch in text if ch.isalnum())


def _amounts(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for match in _MONEY_TOKEN.finditer(text):
        parsed = parse_amount(match.group(1))
        if parsed is not None:
            values.add(parsed.normalize())
    return values


def _parse_date(value: str) -> tuple[int, int, int] | None:
    cleaned = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", value.strip(), flags=re.IGNORECASE)
    for fmt in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d %B %Y",
        "%d %b %Y",
        "%d-%B-%Y",
        "%d-%b-%Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d.%m.%Y",
    ):
        try:
            parsed = datetime.strptime(cleaned.replace(",", ""), fmt)
            return parsed.year, parsed.month, parsed.day
        except ValueError:
            continue
    return None


def _date_supported(candidate: str, transcript: str) -> bool:
    wanted = _parse_date(candidate)
    if wanted is None:
        return _norm(candidate) in _norm(transcript)
    patterns = re.findall(
        r"\b(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|"
        r"\d{1,2}(?:st|nd|rd|th)?(?:\s+|-)\s*[A-Za-z]{3,9}(?:\s+|-)\s*\d{4}|"
        r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b",
        transcript,
        flags=re.IGNORECASE,
    )
    return wanted in {_parse_date(item) for item in patterns}


def _expiry_label_supports(candidate: str, transcript: str) -> bool:
    """Require expiry semantics, not merely the same date elsewhere on a page."""
    wanted = _parse_date(candidate)
    labelled_values = re.findall(
        r"(?im)^\s*(?:expiry\s+date|expiration\s+date|expires\s+on|valid\s+until|"
        r"valid\s+through)\s*[:#-]?\s*([^\r\n]+)",
        transcript,
    )
    if wanted is not None:
        return wanted in {_parse_date(value.strip().rstrip(".,")) for value in labelled_values}
    normalized = _norm(candidate)
    return any(normalized in _norm(value) for value in labelled_values)


def _description_supported(candidate: str, transcript: str) -> bool:
    """Allow a table cell followed by a nearby wrapped continuation line."""
    words = re.findall(r"[A-Za-z0-9]+", unicodedata.normalize("NFKC", candidate))
    if not words:
        return False
    pattern = r".{0,180}".join(re.escape(word.casefold()) for word in words)
    normalized_transcript = unicodedata.normalize("NFKC", transcript).casefold()
    return re.search(pattern, normalized_transcript, flags=re.DOTALL) is not None


# Header totals must be adjacent to their semantic label.
_HEADER_LABELS = {
    "subtotal": r"(?:sub[ -]?total|taxable\s+(?:amount|value))",
    "grand_total": (
        r"(?:(?:grand\s+|invoice\s+|net\s+)?total"
        r"(?:\s+invoice\s+value)?|amount\s+(?:due|payable))"
    ),
    "discount_amount": r"discount(?:\s+amount)?",
}


def _labelled_amount(field_name: str, value: object, transcript: str) -> bool:
    wanted = parse_amount(str(value))
    if wanted is None:
        return False
    matches = re.finditer(
        r"(?im)(?<![\w])"
        + _HEADER_LABELS[field_name]
        + r"(?:[ \t]*\((?:INR|USD|EUR|GBP)\))?[ \t:|=-]*"
        r"((?:(?:INR|USD|EUR|GBP|Rs\.?|₹|\$|€|£)\s*)?\d[\d,.]*)",
        transcript,
    )
    return any(parse_amount(m.group(1)) == wanted for m in matches)


def _row_context(row: dict, transcript: str) -> str:
    description = str(row.get("description") or "")
    if not description:
        return ""
    rows = [line for line in transcript.splitlines() if _norm(description) in _norm(line)]
    return rows[0] if len(rows) == 1 else ""


def _column_context(field_name: str, row: str, transcript: str) -> str:
    """Use the labelled table cell when a row has explicit columns."""
    if "|" not in row or field_name not in _NUMERIC_FIELDS:
        return row
    aliases = {
        "quantity": {"qty", "quantity", "quantityreceived", "receivedqty"},
        "unit_price": {"unitprice", "price", "rate", "unitrate"},
        "line_total": {"amount", "total", "linetotal", "totalamount", "value"},
        "taxable_value": {"taxablevalue", "taxableamount"},
        "rate": {"rate", "taxrate"},
        "cgst": {"cgst"},
        "sgst": {"sgst"},
        "total_tax": {"totaltax", "taxamount"},
    }
    lines = transcript.splitlines()
    positions = [index for index, line in enumerate(lines) if line == row]
    if len(positions) != 1:
        return ""
    cells = row.strip().strip("|").split("|")
    for header in reversed(lines[: positions[0]]):
        headers = header.strip().strip("|").split("|")
        if len(headers) != len(cells):
            continue
        labels = [_norm(re.sub(r"\([^)]*\)", "", value)) for value in headers]
        if not any(
            label in {"description", "descriptionofgoods", "item", "itemdescription", "particulars"}
            for label in labels
        ):
            continue
        matches = [
            index for index, label in enumerate(labels) if label in aliases.get(field_name, set())
        ]
        return cells[matches[0]] if len(matches) == 1 else ""
    return ""


def _supported(field_name: str, value: object, transcript: str) -> bool:
    if value is None or str(value).strip() == "":
        return True
    if field_name in _NUMERIC_FIELDS:
        parsed = parse_amount(str(value))
        if field_name == "quantity" and parsed is None:
            numeric = re.search(r"\d+(?:[,.]\d+)?", str(value))
            parsed = parse_amount(numeric.group(0)) if numeric else None
        return parsed is not None and parsed.normalize() in _amounts(transcript)
    if field_name == "description":
        return _description_supported(str(value), transcript)
    if field_name in _DATE_FIELDS:
        if field_name == "expiry_date":
            return _expiry_label_supports(str(value), transcript)
        return _date_supported(str(value), transcript)
    return _norm(value) in _norm(transcript)


def ground_instance(instance: BaseModel, transcript: str, page: int) -> GroundingResult:
    """Return a same-type model containing only transcription-supported values."""
    issues: list[GroundingIssue] = []

    def visit(value: Any, path: str, field_name: str, context: str = transcript) -> Any:
        if field_name in _ADVISORY_FIELDS:
            return value
        if isinstance(value, dict):
            return {
                key: visit(child, f"{path}.{key}" if path else key, key, context)
                for key, child in value.items()
            }
        if isinstance(value, list):
            grounded_list: list[Any] = []
            for idx, child in enumerate(value):
                row_context = (
                    _row_context(child, context)
                    if isinstance(child, dict)
                    and field_name in {"line_items", "goods", "tax_lines"}
                    else context
                )
                item = visit(child, f"{path}[{idx}]", field_name, row_context)
                if isinstance(item, dict) and field_name == "line_items":
                    # Logistics documents prove movement/receipt, not pricing.
                    logistics = type(instance).__name__ in {
                        "DeliveryChallanExtraction",
                        "GoodsReceiptExtraction",
                    }
                    required: tuple[str, ...] = (
                        ("description", "quantity")
                        if logistics
                        else ("description", "quantity", "unit_price", "line_total")
                    )
                    if not all(item.get(name) not in (None, "") for name in required):
                        issues.append(
                            GroundingIssue(
                                f"{path}[{idx}]",
                                str(child),
                                page,
                                "line item is not fully grounded",
                            )
                        )
                        continue
                if isinstance(item, dict) and field_name == "goods":
                    required = ("description", "hs_code", "quantity")
                    if not all(item.get(name) not in (None, "") for name in required):
                        issues.append(
                            GroundingIssue(
                                f"{path}[{idx}]",
                                str(child),
                                page,
                                "certificate goods row is not fully grounded",
                            )
                        )
                        continue
                grounded_list.append(item)
            return grounded_list
        if "[" in path:
            context = _column_context(field_name, context, transcript)
        header_amount = field_name in _HEADER_LABELS and "[" not in path and value not in (None, "")
        if not (
            _labelled_amount(field_name, value, context)
            if header_amount
            else _supported(field_name, value, context)
        ):
            issues.append(GroundingIssue(path, str(value), page))
            return None
        return value

    grounded_data = visit(instance.model_dump(mode="python"), "", "")
    return GroundingResult(instance=type(instance).model_validate(grounded_data), issues=issues)
