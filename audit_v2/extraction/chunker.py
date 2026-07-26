from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class TextChunk:
    chunk_id: str
    source: str
    page: int
    bbox: list[float] | None
    text: str
    embedding: list[float] | None = None


def chunk_text(
    text: str,
    source: str,
    page: int = 1,
    bbox: list[float] | None = None,
) -> list[TextChunk]:
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks: list[TextChunk] = []
    for para in paragraphs:
        para = para.strip()
        if len(para) < 20:
            continue
        if len(para) <= 500:
            chunk_id = f"chk_{source}_{page}_{len(chunks)}"
            chunks.append(
                TextChunk(chunk_id=chunk_id, source=source, page=page, bbox=bbox, text=para)
            )
        else:
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current = ""
            for sent in sentences:
                if len(current) + len(sent) < 500 and current:
                    current += " " + sent
                else:
                    if current:
                        chunk_id = f"chk_{source}_{page}_{len(chunks)}"
                        chunks.append(
                            TextChunk(
                                chunk_id=chunk_id, source=source, page=page,
                                bbox=bbox, text=current,
                            )
                        )
                    current = sent
            if current:
                chunk_id = f"chk_{source}_{page}_{len(chunks)}"
                chunks.append(
                    TextChunk(chunk_id=chunk_id, source=source, page=page, bbox=bbox, text=current)
                )
    return chunks
