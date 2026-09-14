"""OpenRouter LLM Gateway for cross-check and text reasoning.

Uses the OpenAI client configured for OpenRouter (https://openrouter.ai/api/v1).
Supports extended reasoning models (e.g. nvidia/nemotron-3-ultra-550b-a55b:free),
PII redaction, token tracking, multi-turn reasoning preservation, and robust retry.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any

from openai import OpenAI

from audit_v2.gateway.pii_redactor import redact
from audit_v2.gateway.vlm_gateway import ModelResponse

logger = logging.getLogger(__name__)

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "inclusionai/ling-3.0-flash-fin:free"


class OpenRouterGateway:
    """Gateway for OpenRouter's OpenAI-compatible completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int = 60,
        max_retries: int = 2,
        enable_reasoning: bool = True,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = (
            model
            or os.getenv("OPENROUTER_MODEL")
            or os.getenv("CROSS_CHECK_MODEL")
            or DEFAULT_OPENROUTER_MODEL
        )
        base = base_url or os.getenv("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL
        self.base_url = base.rstrip("/")
        self.timeout = (
            timeout
            if timeout != 60
            else int(os.getenv("OPENROUTER_TIMEOUT", "60"))
        )
        self.max_retries = (
            max_retries
            if max_retries != 2
            else int(os.getenv("OPENROUTER_MAX_RETRIES", "2"))
        )
        self.enable_reasoning = enable_reasoning

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key or "sk-dummy-unconfigured",
            timeout=float(self.timeout),
        )

    def extract(
        self,
        images: list[bytes],
        prompt: str,
        tenant_id: str,
        pii_classes: list[str] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> ModelResponse:
        """Call OpenRouter model with prompt and optional schema/images."""
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable or api_key parameter is required"
            )

        clean_prompt = redact(prompt, pii_classes=pii_classes)

        if response_schema is not None:
            clean_prompt = (
                f"{clean_prompt}\n\n"
                "Return ONLY a valid JSON object matching this schema:\n"
                f"{json.dumps(response_schema)}"
            )

        messages: list[dict[str, Any]]
        if images:
            content_parts: list[dict[str, Any]] = [{"type": "text", "text": clean_prompt}]
            for img_bytes in images:
                b64_str = base64.b64encode(img_bytes).decode("utf-8")
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"},
                    }
                )
            messages = [{"role": "user", "content": content_parts}]
        else:
            messages = [{"role": "user", "content": clean_prompt}]

        extra_body: dict[str, Any] = {}
        if self.enable_reasoning:
            extra_body["reasoning"] = {"enabled": True}

        start_time = time.monotonic()
        attempt = 0
        max_attempts = self.max_retries + 1
        last_error: Exception | None = None

        while attempt < max_attempts:
            attempt += 1
            logger.info(
                "OpenRouterGateway call attempt %d/%d for tenant %s (model=%s)",
                attempt,
                max_attempts,
                tenant_id,
                self.model,
            )
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    extra_body=extra_body if extra_body else None,
                    timeout=float(self.timeout),
                )
                latency_ms = (time.monotonic() - start_time) * 1000.0

                choice = response.choices[0]
                message = choice.message
                content = message.content or ""

                usage = getattr(response, "usage", None)
                tokens_prompt = getattr(usage, "prompt_tokens", 0) if usage else 0
                tokens_completion = getattr(usage, "completion_tokens", 0) if usage else 0

                return ModelResponse(
                    content=content,
                    model_version=self.model,
                    tokens_prompt=tokens_prompt,
                    tokens_completion=tokens_completion,
                    latency_ms=latency_ms,
                )
            except Exception as err:
                last_error = err
                logger.warning(
                    "OpenRouterGateway attempt %d/%d error for tenant %s: %s",
                    attempt,
                    max_attempts,
                    tenant_id,
                    err,
                )
                if attempt < max_attempts:
                    time.sleep(min(2 ** attempt, 8))

        raise RuntimeError(
            f"OpenRouterGateway request failed after {max_attempts} attempts: {last_error}"
        ) from last_error

    def extract_limited(
        self,
        images: list[bytes],
        prompt: str,
        tenant_id: str,
        max_tokens: int,
        pii_classes: list[str] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> ModelResponse:
        return self.extract(
            images=images,
            prompt=prompt,
            tenant_id=tenant_id,
            pii_classes=pii_classes,
            response_schema=response_schema,
        )

    def chat_multi_turn(
        self,
        messages: list[dict[str, Any]],
        enable_reasoning: bool | None = None,
    ) -> Any:
        """Multi-turn completions endpoint preserving reasoning_details."""
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable or api_key parameter is required"
            )

        reasoning = self.enable_reasoning if enable_reasoning is None else enable_reasoning
        extra_body: dict[str, Any] = {}
        if reasoning:
            extra_body["reasoning"] = {"enabled": True}

        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            extra_body=extra_body if extra_body else None,
            timeout=float(self.timeout),
        )
