from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

AMOUNT_CLEAN_RE = re.compile(r"^(?:INR|Rs\.?|USD|EUR|GBP|₹|\$|€|£)?\s*(.*)", re.IGNORECASE)
ACCOUNTING_NEG_RE = re.compile(r"^\((.*)\)$")

DATE_FORMATS = [
    ("%d/%m/%Y", re.compile(r"^\d{2}/\d{2}/\d{4}$")),
    ("%d-%m-%Y", re.compile(r"^\d{2}-\d{2}-\d{4}$")),
    ("%d-%m-%y", re.compile(r"^\d{2}-\d{2}-\d{2}$")),
    ("%Y-%m-%d", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("%Y/%m/%d", re.compile(r"^\d{4}/\d{2}/\d{2}$")),
    ("%d.%m.%Y", re.compile(r"^\d{2}\.\d{2}\.\d{4}$")),
]

MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}\d[Z]{1}[A-Z\d]{1}$")
HSN_RE = re.compile(r"^\d{4,8}$")
PO_REF_SHORT_RE = re.compile(
    r"(?<![A-Za-z0-9])((?:PO|P\.?O\.?)[\s.:#/-]+[A-Za-z0-9][A-Za-z0-9/-]+)",
    re.IGNORECASE,
)
PO_REF_LONG_RE = re.compile(
    r"Purchase\s+Order\s*[#:]+\s*([A-Za-z0-9][A-Za-z0-9/-]+)",
    re.IGNORECASE,
)
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def parse_amount(raw: str, locale_hint: str | None = None) -> Decimal | None:
    cleaned = AMOUNT_CLEAN_RE.sub(r"\1", raw.strip()).strip()
    # OCR/VLM output commonly writes ISO currency after the value (for
    # example ``828.69 EUR``). Currency is retained separately by the mapper;
    # it must not make an otherwise visible amount unparseable.
    cleaned = re.sub(r"\s*(?:INR|Rs\.?|USD|EUR|GBP|₹|\$|€|£)\s*$", "", cleaned, flags=re.I)
    if not cleaned:
        return None

    negative = False
    m = ACCOUNTING_NEG_RE.match(cleaned)
    if m:
        negative = True
        cleaned = m.group(1)

    cleaned = cleaned.replace(" ", "")

    if locale_hint == "de-DE" or locale_hint == "fr-FR":
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif locale_hint == "en-IN" or locale_hint == "en-US":
        cleaned = cleaned.replace(",", "")
    else:
        if cleaned.startswith(".") or cleaned.endswith("."):
            return None
        has_dot = "." in cleaned
        has_comma = "," in cleaned
        if not has_dot and not has_comma:
            pass
        elif has_dot and has_comma:
            dot_pos = cleaned.rfind(".")
            comma_pos = cleaned.rfind(",")
            if dot_pos > comma_pos:
                cleaned = cleaned.replace(",", "")
            else:
                cleaned = cleaned.replace(".", "").replace(",", ".")
        elif has_comma and not has_dot:
            cleaned = cleaned.replace(",", "")
        elif has_dot and not has_comma:
            parts = cleaned.split(".")
            if len(parts) == 2 and len(parts[1]) == 3 and parts[0]:
                return None

    try:
        val = Decimal(cleaned)
        return -val if negative else val
    except Exception:
        return None


def normalize_locale(raw: str, locale: str | None) -> str:
    parsed = parse_amount(raw, locale)
    return str(parsed) if parsed is not None else raw


def parse_date(raw: str) -> date | None:
    stripped = raw.strip()
    for fmt, pattern in DATE_FORMATS:
        if pattern.match(stripped):
            try:
                return datetime.strptime(stripped, fmt).date()
            except ValueError:
                pass

    # Generic smart parsing to resolve MM/DD vs DD/MM ambiguity
    cleaned = stripped.replace("-", " ").replace("/", " ").replace(".", " ")
    parts = cleaned.split()
    if len(parts) == 3:
        p1, p2, p3 = parts
        p2_lower = p2.lower()[:3]
        if p2_lower in MONTH_NAMES:
            try:
                day_val = int(p1)
                year_val = int(p3)
                if year_val < 100:
                    year_val += 2000
                return date(year_val, MONTH_NAMES[p2_lower], day_val)
            except ValueError:
                pass

        if p1.isdigit() and p2.isdigit() and p3.isdigit():
            v1, v2, v3 = int(p1), int(p2), int(p3)
            # Determine year
            if v3 > 31:  # Year is v3
                year_val = v3
                if year_val < 100:
                    year_val += 2000
                # Resolve ambiguity
                if v1 > 12 and v2 <= 12:  # DD/MM/YYYY
                    return date(year_val, v2, v1)
                elif v2 > 12 and v1 <= 12:  # MM/DD/YYYY
                    return date(year_val, v1, v2)
                elif v1 <= 12 and v2 <= 12:  # Ambiguous, default to DD/MM/YYYY
                    return date(year_val, v2, v1)
            elif v1 > 31:  # Year is v1 (YYYY/MM/DD)
                year_val = v1
                if v2 <= 12 and v3 <= 31:
                    return date(year_val, v2, v3)

    return None


def validate_gstin(gstin: str) -> bool:
    return bool(GSTIN_RE.match(gstin.strip().upper()))


def validate_hsn(code: str) -> bool:
    return bool(HSN_RE.match(code.strip()))


def validate_ifsc(ifsc: str) -> bool:
    return bool(IFSC_RE.match(ifsc.strip().upper()))


def extract_po_reference(text: str) -> str | None:
    m = PO_REF_SHORT_RE.search(text)
    if m:
        candidate = m.group(1).strip()
        if re.fullmatch(r"(?i)P\.?O\.?(?:\s+Reference|\s+Number|\s+No\.?)", candidate):
            return None
        return candidate
    m = PO_REF_LONG_RE.search(text)
    if m:
        return m.group(1).strip()
    return None
