from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TextExtractor:
    def extract_text_blocks(self, data: bytes) -> list[dict[str, Any]]:
        try:
            import fitz  # type: ignore[import-untyped]  # noqa: F811
        except ImportError as e:
            logger.warning("PyMuPDF (fitz) not installed — cannot extract PDF text blocks")
            raise RuntimeError("PyMuPDF (fitz) is required for PDF text extraction") from e

        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as e:
            logger.error("Failed to open PDF: %s", e)
            raise RuntimeError(f"Failed to open PDF: {e}") from e

        blocks: list[dict[str, Any]] = []
        try:
            for page_num in range(doc.page_count):
                page = doc.load_page(page_num)
                page_dict = page.get_text("dict")
                for block in page_dict.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    # Spans are column cells and lines are table rows. Joining
                    # either without a separator fuses adjacent numeric columns
                    # into one token (e.g. HSN 8471 + qty 2 + rate 45,000.00 ->
                    # "8471245,000.00"), which silently corrupts extraction.
                    rendered_lines = []
                    for line in block.get("lines", []):
                        spans = [
                            span.get("text", "").strip()
                            for span in line.get("spans", [])
                        ]
                        joined = "\t".join(s for s in spans if s)
                        if joined:
                            rendered_lines.append(joined)
                    text = "\t".join(rendered_lines).strip()
                    if not text:
                        continue
                    bbox = block.get("bbox")
                    blocks.append({
                        "text": text,
                        "page": page_num + 1,
                        "bbox": list(bbox) if bbox else None,
                        "block_type": "text",
                    })
        finally:
            doc.close()

        return blocks

    def has_text_layer(self, data: bytes) -> bool:
        blocks = self.extract_text_blocks(data)
        return len(blocks) > 0

    def extract_page_texts(self, data: bytes) -> dict[int, str]:
        blocks = self.extract_text_blocks(data)
        page_texts: dict[int, str] = {}
        for block in blocks:
            page = block["page"]
            if page not in page_texts:
                page_texts[page] = ""
            page_texts[page] += block["text"] + "\n"
        return page_texts
