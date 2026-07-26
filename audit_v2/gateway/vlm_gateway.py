"""VLM Gateway — model access layer with retry, caching, and redaction.

The gateway is the only component that makes network calls to model APIs.
It handles: retry with backoff, response validation, PII redaction pre-call,
and per-tenant token budgeting.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ModelResponse:
    content: str
    model_version: str
    tokens_prompt: int = 0
    tokens_completion: int = 0
    latency_ms: float = 0.0


class ModelGateway(ABC):
    @abstractmethod
    async def extract(self, image_bytes: bytes, prompt: str, tenant_id: str) -> ModelResponse:
        ...

    @abstractmethod
    async def classify(self, image_bytes: bytes, tenant_id: str) -> ModelResponse:
        ...


class GeminiGateway(ModelGateway):
    async def extract(self, image_bytes: bytes, prompt: str, tenant_id: str) -> ModelResponse:
        return ModelResponse(content="{}", model_version="gemini-2.5-flash-002")

    async def classify(self, image_bytes: bytes, tenant_id: str) -> ModelResponse:
        return ModelResponse(content="{}", model_version="gemini-2.5-flash-002")
