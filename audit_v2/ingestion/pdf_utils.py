from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MAX_PAGE_COUNT = 500
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024
SUPPORTED_MIME_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png"})


def is_supported_mime(mime: str) -> bool:
    return mime in SUPPORTED_MIME_TYPES


def is_valid_page_count(pages: int) -> bool:
    return 1 <= pages <= MAX_PAGE_COUNT


def is_valid_file_size(size_bytes: int) -> bool:
    return 0 < size_bytes <= MAX_FILE_SIZE_BYTES


def is_zero_byte(size_bytes: int) -> bool:
    return size_bytes == 0


def is_encrypted_pdf(data: bytes) -> bool:
    return b"/Encrypt" in data


def has_text_layer(data: bytes) -> bool:
    try:
        import fitz  # type: ignore[import-untyped]  # noqa: F811

        doc = fitz.open(stream=data, filetype="pdf")
        try:
            for page_num in range(min(doc.page_count, 5)):
                text = doc[page_num].get_text().strip()
                if text:
                    return True
            return False
        finally:
            doc.close()
    except ImportError:
        logger.warning("PyMuPDF (fitz) not installed — cannot check PDF text layer")
        return False
    except Exception as e:
        logger.error("Failed to check PDF text layer: %s", e)
        return False


def count_pdf_pages(data: bytes) -> int | None:
    try:
        import fitz  # type: ignore[import-untyped]  # noqa: F811

        doc = fitz.open(stream=data, filetype="pdf")
        try:
            return doc.page_count
        finally:
            doc.close()
    except ImportError:
        logger.warning("PyMuPDF (fitz) not installed — cannot count PDF pages")
        return None
    except Exception as e:
        logger.error("Failed to count PDF pages: %s", e)
        return None
