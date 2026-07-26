from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Span:
    start: int
    end: int
    label: str


PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("gstin", re.compile(r"\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z]\d", re.IGNORECASE)),
    ("pan", re.compile(r"[A-Z]{5}\d{4}[A-Z]", re.IGNORECASE)),
    ("ifsc", re.compile(r"[A-Z]{4}0[A-Z0-9]{6}", re.IGNORECASE)),
    ("bank_account", re.compile(r"\b\d{9,18}\b")),
    ("phone", re.compile(r"\b(?:\+91[-\s]?)?[6-9]\d{9}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]


def classify_pii(text: str) -> dict[str, list[Span]]:
    results: dict[str, list[Span]] = {}
    for label, pattern in PII_PATTERNS:
        spans = []
        for m in pattern.finditer(text):
            spans.append(Span(start=m.start(), end=m.end(), label=label))
        if spans:
            results[label] = spans
    return results


def redact(text: str, pii_classes: list[str] | None = None) -> str:
    if pii_classes is None:
        pii_classes = [label for label, _ in PII_PATTERNS]

    spans: list[Span] = []
    for label, pattern in PII_PATTERNS:
        if label not in pii_classes:
            continue
        for m in pattern.finditer(text):
            spans.append(Span(start=m.start(), end=m.end(), label=label))

    spans.sort(key=lambda s: s.start, reverse=True)

    result = text
    for span in spans:
        result = result[:span.start] + f"[REDACTED_{span.label.upper()}]" + result[span.end:]

    return result
