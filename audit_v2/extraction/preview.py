"""Page-1 thumbnail preview as base64 JPEG (ported from V1 runner._generate_preview)."""
from __future__ import annotations

import base64
from io import BytesIO

from audit_v2.extraction.vlm_extractor import render_pages_to_jpeg


def generate_preview(data: bytes, mime_type: str, max_size: int = 180) -> str:
    try:
        from PIL import Image

        pages = render_pages_to_jpeg(data, mime_type)
        if not pages:
            return ""
        img = Image.open(BytesIO(pages[0]))
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""
