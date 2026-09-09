"""Common synchronous interface for document-vision gateways."""

from __future__ import annotations

from typing import Any, Protocol

from audit_v2.gateway.vlm_gateway import ModelResponse


class ExtractionGateway(Protocol):
    """Minimal contract consumed by structured extraction and the pipeline."""

    def extract(
        self,
        images: list[bytes],
        prompt: str,
        tenant_id: str,
        pii_classes: list[str] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> ModelResponse: ...


class VisionGateway(ExtractionGateway, Protocol):
    """A document-image gateway also exposes model identity and health."""

    @property
    def model(self) -> str: ...

    @property
    def backend(self) -> str: ...

    def health(self) -> dict[str, Any]: ...
