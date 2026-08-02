"""NVIDIA VLM Gateway — Phase 4 completion & Phase 5.1 (PHASES_V2 §4).

Multimodal model access layer connecting to NVIDIA's OpenAI-compatible API
(https://integrate.api.nvidia.com/v1). Automatically redacts PII pre-call
(Phase 2 governance) and retries on transient errors.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any

import requests

from audit_v2.gateway.pii_redactor import redact
from audit_v2.gateway.vlm_gateway import ModelResponse

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "google/diffusiongemma-26b-a4b-it"


class NvidiaGateway:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int = 120,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.model = model or os.getenv("NVIDIA_MODEL", DEFAULT_MODEL)
        base = base_url or os.getenv("NVIDIA_BASE_URL", DEFAULT_BASE_URL)
        self.base_url = base.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def extract(
        self,
        images: list[bytes],
        prompt: str,
        tenant_id: str,
        pii_classes: list[str] | None = None,
    ) -> ModelResponse:
        """Send page images + prompt to NVIDIA VLM API.

        Parameters
        ----------
        images : list[bytes]
            Raw image bytes (JPEG/PNG) for each document page.
        prompt : str
            Instruction prompt asking for structured JSON extraction.
        tenant_id : str
            Tenant identifier for logging / token budget tracking.
        pii_classes : list[str] | None
            PII classes to redact from the prompt before sending.

        Returns
        -------
        ModelResponse
            Parsed content string and token usage metadata.
        """
        if not self.api_key:
            raise ValueError(
                "NVIDIA_API_KEY environment variable or api_key parameter is required"
            )

        # PHASES_V2 §4 Phase 2: Redact PII in text prompt before model call
        clean_prompt = redact(prompt, pii_classes=pii_classes)

        # Base64 encode images for data URL content parts
        content_parts: list[dict[str, Any]] = [
            {"type": "text", "text": clean_prompt}
        ]
        for img_bytes in images:
            b64_str = base64.b64encode(img_bytes).decode("utf-8")
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"},
            })

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content_parts}],
            "max_tokens": 4096,
            "temperature": 0.1,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"
        start_time = time.monotonic()
        attempt = 0
        last_error: Exception | None = None

        while attempt <= self.max_retries:
            attempt += 1
            try:
                logger.info(
                    "NvidiaGateway call attempt %d for tenant %s (%d page images)",
                    attempt, tenant_id, len(images),
                )
                resp = requests.post(
                    url, headers=headers, json=payload, timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                latency_ms = (time.monotonic() - start_time) * 1000

                choice: str = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                tokens_prompt = usage.get("prompt_tokens", 0)
                tokens_completion = usage.get("completion_tokens", 0)

                return ModelResponse(
                    content=choice,
                    model_version=self.model,
                    tokens_prompt=tokens_prompt,
                    tokens_completion=tokens_completion,
                    latency_ms=latency_ms,
                )

            except (requests.RequestException, KeyError, json.JSONDecodeError) as err:
                last_error = err
                logger.warning(
                    "NvidiaGateway attempt %d failed for tenant %s: %s",
                    attempt, tenant_id, err,
                )
                if attempt <= self.max_retries:
                    time.sleep(2 ** attempt)

        raise RuntimeError(
            f"NvidiaGateway failed after {self.max_retries + 1} attempts: {last_error}"
        ) from last_error
