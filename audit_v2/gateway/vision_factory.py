"""Configuration-driven construction of the local V2 vision gateway."""
from __future__ import annotations

import os

from audit_v2.gateway.glm_ocr_gateway import GlmOcrGateway
from audit_v2.gateway.qwen_vl_gateway import QwenVlGateway
from audit_v2.gateway.vision_gateway import VisionGateway


def configured_vision_backend() -> str:
    """Return the normalized configured backend name."""
    return os.getenv("V2_VISION_BACKEND", "qwen_ollama").strip().lower()


def create_vision_gateway() -> VisionGateway | None:
    """Create the selected local gateway, or ``None`` when disabled."""
    backend = configured_vision_backend()
    if backend in {"qwen", "qwen_ollama", "ollama"}:
        return QwenVlGateway()
    if backend in {"glm", "glm_ocr"}:
        return GlmOcrGateway()
    if backend == "none":
        return None
    raise ValueError(f"Unsupported V2_VISION_BACKEND: {backend}")
