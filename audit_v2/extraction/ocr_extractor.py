"""RapidOCR text extraction (new_requirements.md §3).

A thin, dependency-optional wrapper around ``rapidocr-onnxruntime`` (CPU/ONNX,
no external binary). It is the middle rung of the math-doc evidence ladder
(regex → **OCR** → VLM): a second, independent read of the page pixels used to
corroborate or challenge what regex and the VLM report.

Design constraints:
- **Never crash the pipeline.** If the package (or its ONNX models) is missing,
  every method returns an ``available=False`` result with a human-readable note
  rather than raising. The caller emits an "OCR unavailable" evidence and
  continues on regex + VLM.
- **Lazy + cached engine.** ``RapidOCR()`` loads a few ONNX models; build it
  once on first use and reuse it (models ship inside the wheel, so no network).
"""

from __future__ import annotations

import logging
import re
from contextlib import suppress
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from audit_v2.domain.models import DocumentType
from audit_v2.extraction.parser import extract_po_reference, parse_amount

logger = logging.getLogger(__name__)

# A money-looking token: optional symbol, digit groups with , or . separators,
# at least one digit. Deliberately loose — OCR text is noisy and we only use
# these as corroboration candidates, never as authoritative values.
_MONEY_RE = re.compile(
    r"(?:INR|Rs\.?|USD|EUR|GBP|₹|\$|€|£)?\s*"
    r"(\d{1,3}(?:[,\s]\d{2,3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
)
_GSTIN_TOKEN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]\b")
_LABELLED_TOTAL_RE = re.compile(
    r"(?:grand\s+total|invoice\s+total|amount\s+payable|net\s+amount|total\s+amount)"
    r"\s*[:\-]?\s*(?:INR|Rs\.?|USD|EUR|GBP|₹|\$|€|£)?\s*"
    r"([0-9][0-9,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)


@dataclass
class OcrPageText:
    page: int
    lines: list[str] = field(default_factory=list)
    mean_confidence: float = 0.0

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass
class OcrResult:
    """Outcome of an OCR pass. ``available`` is False when OCR could not run."""

    available: bool
    pages: list[OcrPageText] = field(default_factory=list)
    note: str | None = None

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    @property
    def mean_confidence(self) -> float:
        confs = [p.mean_confidence for p in self.pages if p.lines]
        return round(sum(confs) / len(confs), 4) if confs else 0.0


# Module-level engine cache. RapidOCR construction is heavy (loads det/cls/rec
# ONNX models); we want exactly one instance per process, built lazily so an
# environment without the package pays nothing and never crashes on import.
class OcrEngine(Protocol):
    def __call__(self, image: bytes) -> tuple[list[list[Any]] | None, Any]: ...


_ENGINE: OcrEngine | None = None
_ENGINE_TRIED = False
_ENGINE_ERROR: str | None = None


def _get_engine() -> OcrEngine | None:
    """Return a cached RapidOCR engine, or None if it cannot be constructed."""
    global _ENGINE, _ENGINE_TRIED, _ENGINE_ERROR
    if _ENGINE_TRIED:
        return _ENGINE
    _ENGINE_TRIED = True
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-untyped]
    except ImportError as err:
        _ENGINE_ERROR = f"rapidocr-onnxruntime not installed ({err})"
        logger.info("OCR unavailable: %s", _ENGINE_ERROR)
        return None
    try:
        _ENGINE = RapidOCR()
    except Exception as err:  # model load / onnxruntime init failure
        _ENGINE_ERROR = f"RapidOCR engine failed to initialize ({err})"
        logger.warning("OCR unavailable: %s", _ENGINE_ERROR)
        _ENGINE = None
    return _ENGINE


class RapidOcrExtractor:
    """Recognize text from page images via RapidOCR, degrading gracefully."""

    def extract_text(self, images: list[bytes]) -> OcrResult:
        engine = _get_engine()
        if engine is None:
            return OcrResult(available=False, note=_ENGINE_ERROR or "OCR unavailable")

        pages: list[OcrPageText] = []
        for idx, img in enumerate(images, start=1):
            try:
                # RapidOCR accepts raw image bytes; returns (list|None, elapse).
                raw, _elapse = engine(img)
            except Exception as err:
                logger.warning("OCR failed on page %d: %s", idx, err)
                pages.append(OcrPageText(page=idx))
                continue
            lines: list[str] = []
            scores: list[float] = []
            for entry in raw or []:
                # entry == [box, text, score]
                if len(entry) >= 3 and entry[1]:
                    lines.append(str(entry[1]).strip())
                    with suppress(TypeError, ValueError):
                        scores.append(float(entry[2]))
            mean_conf = round(sum(scores) / len(scores), 4) if scores else 0.0
            pages.append(OcrPageText(page=idx, lines=lines, mean_confidence=mean_conf))
        return OcrResult(available=True, pages=pages)

    def extract_fields(self, images: list[bytes], doc_type: DocumentType) -> dict:
        """Coarse field read from OCR text, for cross-method corroboration.

        These are *candidates*, not authoritative values. Monetary totals are
        emitted only when a total label anchors the number; the largest bare
        number may be a certificate number, HS code, quantity, or date.
        """
        result = self.extract_text(images)
        if not result.available:
            return {"available": False, "note": result.note}

        text = result.full_text
        amounts = self._amounts(text)
        grand_total = (
            self._labelled_total(text)
            if doc_type
            in {
                DocumentType.INVOICE,
                DocumentType.PURCHASE_ORDER,
            }
            else None
        )
        fields: dict = {
            "available": True,
            "mean_confidence": result.mean_confidence,
            "po_reference": extract_po_reference(text),
            "gstins": _GSTIN_TOKEN_RE.findall(text.upper()),
            "grand_total": str(grand_total) if grand_total is not None else None,
            "amount_candidates": [str(a) for a in amounts],
        }
        return fields

    @staticmethod
    def _labelled_total(text: str) -> Decimal | None:
        matches = [parse_amount(match.group(1)) for match in _LABELLED_TOTAL_RE.finditer(text)]
        values = [value for value in matches if value is not None]
        return values[-1] if values else None

    @staticmethod
    def _amounts(text: str) -> list[Decimal]:
        vals: list[Decimal] = []
        for match in _MONEY_RE.finditer(text):
            parsed = parse_amount(match.group(1))
            # Ignore bare small integers (line numbers, quantities, years) —
            # they inflate the "largest amount" anchor with noise.
            if parsed is not None and parsed >= Decimal("100"):
                vals.append(parsed)
        return vals
