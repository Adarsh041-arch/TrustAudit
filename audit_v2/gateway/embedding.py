from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingGateway(ABC):
    @abstractmethod
    def generate(self, text: str) -> list[float]: ...


class StubEmbeddingGateway(EmbeddingGateway):
    DIMENSION = 384

    def generate(self, text: str) -> list[float]:
        return [0.0] * self.DIMENSION
