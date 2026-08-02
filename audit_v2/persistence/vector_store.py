from __future__ import annotations

from abc import ABC, abstractmethod

from audit_v2.extraction.chunker import TextChunk


class VectorStore(ABC):
    @abstractmethod
    def insert(self, chunk: TextChunk) -> None: ...
    @abstractmethod
    def search(self, query: list[float], tenant_id: str, top_k: int = 10) -> list[TextChunk]: ...
    @abstractmethod
    def delete_by_source(self, source: str) -> None: ...


class MemoryVectorStore(VectorStore):
    def __init__(self):
        self._chunks: dict[str, TextChunk] = {}

    def insert(self, chunk: TextChunk) -> None:
        self._chunks[chunk.chunk_id] = chunk

    def search(self, query: list[float], tenant_id: str, top_k: int = 10) -> list[TextChunk]:
        return list(self._chunks.values())[:top_k]

    def delete_by_source(self, source: str) -> None:
        self._chunks = {k: v for k, v in self._chunks.items() if v.source != source}
