"""Prompt-injection detection for untrusted document content (PHASES_V2 §5).

Documents are adversarial input: the attacker's goal is a clean audit report on
a fraudulent invoice. This module implements control 3 (injection detection) and
control 4 (invisible-text detection).

It is a detector, not a sanitiser. Detection routes the document to
QUARANTINED_SECURITY; it never "cleans" content and continues. The deterministic
validation engine remains the real backstop: an injection can corrupt
extraction, but it cannot make 5 x 30 = 200 true in Python.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Instruction-shaped text that has no legitimate reason to appear in an invoice.
INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("override_instruction", re.compile(
        r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}"
        r"\b(?:previous|prior|above|earlier|all)\b[^.\n]{0,20}"
        r"\b(?:instruction|prompt|rule|direction|context)",
        re.IGNORECASE)),
    ("role_assertion", re.compile(
        r"\b(?:as an? AI|you are (?:now )?an?|act as|pretend to be|"
        r"your new (?:role|task|instruction))\b",
        re.IGNORECASE)),
    ("compliance_assertion", re.compile(
        r"\b(?:report|mark|treat|classify|score|declare)\b[^.\n]{0,30}"
        r"\b(?:as )?(?:compliant|approved|passed|valid|clean|no issues?)\b",
        re.IGNORECASE)),
    ("audit_suppression", re.compile(
        r"\b(?:skip|bypass|do not (?:perform|run|report)|suppress|omit)\b"
        r"[^.\n]{0,30}\b(?:check|audit|validation|verification|finding)",
        re.IGNORECASE)),
    ("chat_role_marker", re.compile(
        r"(?:^|\n)\s*(?:system|assistant|user)\s*:\s", re.IGNORECASE)),
    ("delimiter_injection", re.compile(
        r"(?:<\|(?:im_start|im_end|endoftext)\|>|\[INST\]|<<SYS>>|```\s*system)",
        re.IGNORECASE)),
]

# Anything at or below this alpha is effectively invisible to a human reader.
_INVISIBLE_ALPHA = 0.05
_MIN_VISIBLE_FONT_SIZE = 1.0


@dataclass
class InjectionSignal:
    kind: str
    detail: str
    page: int | None = None
    excerpt: str = ""


@dataclass
class InjectionScanResult:
    signals: list[InjectionSignal] = field(default_factory=list)

    @property
    def is_suspicious(self) -> bool:
        return bool(self.signals)

    def summary(self) -> str:
        if not self.signals:
            return "no injection signals"
        kinds = sorted({s.kind for s in self.signals})
        return f"{len(self.signals)} signal(s): {', '.join(kinds)}"


def scan_text(text: str, page: int | None = None) -> list[InjectionSignal]:
    """Detect instruction-like content in extracted document text."""
    signals: list[InjectionSignal] = []
    for kind, pattern in INJECTION_PATTERNS:
        for m in pattern.finditer(text):
            excerpt = text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")
            signals.append(InjectionSignal(
                kind=kind,
                detail=f"matched {kind} pattern",
                page=page,
                excerpt=excerpt.strip(),
            ))
    return signals


def scan_pdf_for_invisible_text(data: bytes) -> list[InjectionSignal]:
    """Detect white-on-white, zero-size, or off-canvas text.

    Legitimate documents do not carry hidden text; its presence is itself a
    finding regardless of what the hidden text says.
    """
    try:
        import fitz  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("PyMuPDF unavailable — skipping invisible-text scan")
        return []

    signals: list[InjectionSignal] = []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:
        logger.error("Invisible-text scan could not open PDF: %s", e)
        return []

    try:
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_rect = page.rect
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 0:
                    continue
                for pdf_line in block.get("lines", []):
                    for span in pdf_line.get("spans", []):
                        content = span.get("text", "").strip()
                        if not content:
                            continue
                        size = span.get("size", 12.0)
                        if size < _MIN_VISIBLE_FONT_SIZE:
                            signals.append(InjectionSignal(
                                kind="zero_size_font",
                                detail=f"font size {size}",
                                page=page_num + 1,
                                excerpt=content[:80],
                            ))
                            continue
                        if _is_near_white(span.get("color", 0)) and not _has_dark_backing(
                            page, span.get("bbox")
                        ):
                            signals.append(InjectionSignal(
                                kind="invisible_text_colour",
                                detail=f"colour {span.get('color')}",
                                page=page_num + 1,
                                excerpt=content[:80],
                            ))
                            continue
                        bbox = span.get("bbox")
                        if bbox and not _intersects(bbox, page_rect):
                            signals.append(InjectionSignal(
                                kind="off_canvas_text",
                                detail=f"bbox {bbox} outside page {tuple(page_rect)}",
                                page=page_num + 1,
                                excerpt=content[:80],
                            ))
    finally:
        doc.close()

    return signals


def _is_near_white(color: int) -> bool:
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF
    return min(r, g, b) >= 255 - int(255 * _INVISIBLE_ALPHA)


def _has_dark_backing(page, bbox) -> bool:
    """True when the span sits on a dark fill, i.e. white text is legible.

    Table headers are routinely white-on-dark. Treating colour alone as
    "invisible" would quarantine most well-formatted invoices.
    """
    if bbox is None:
        return False
    try:
        import fitz  # type: ignore[import-untyped]

        rect = fitz.Rect(bbox)
        for drawing in page.get_drawings():
            fill = drawing.get("fill")
            if fill is None:
                continue
            if max(fill) > 0.6:
                continue
            if fitz.Rect(drawing["rect"]).intersects(rect):
                return True
    except Exception:
        return False
    return False


def _intersects(bbox: list[float] | tuple[float, ...], page_rect) -> bool:
    x0, y0, x1, y1 = bbox
    return not (
        x1 < page_rect.x0 or x0 > page_rect.x1
        or y1 < page_rect.y0 or y0 > page_rect.y1
    )


def scan_document(text: str, data: bytes | None = None) -> InjectionScanResult:
    """Full §5 scan: instruction patterns in text plus hidden text in the PDF."""
    signals = scan_text(text)
    if data is not None:
        signals.extend(scan_pdf_for_invisible_text(data))
    result = InjectionScanResult(signals=signals)
    if result.is_suspicious:
        logger.warning("Prompt-injection scan flagged document: %s", result.summary())
    return result
