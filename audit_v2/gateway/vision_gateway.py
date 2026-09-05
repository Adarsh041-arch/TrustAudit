"""Common synchronous interface for document-vision gateways."""
from __future__ import annotations

from typing import Any, Protocol

from audit_v2.gateway.vlm_gateway import ModelResponse


class VisionGateway(Protocol):
    """Minimal contract consumed by structured extraction and the pipeline."""

    model: str
    backend: str

    def extract(
        self,
        images: list[bytes],
        prompt: str,
        tenant_id: str,
        pii_classes: list[str] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> ModelResponse: ...

    def health(self) -> dict[str, Any]: ...
