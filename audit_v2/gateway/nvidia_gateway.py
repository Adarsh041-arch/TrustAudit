"""NVIDIA VLM Gateway — Phase 4 completion & Phase 5.1 (PHASES_V2 §4).

Multimodal model access layer connecting to NVIDIA's OpenAI-compatible API
(https://integrate.api.nvidia.com/v1). Automatically redacts PII pre-call
(Phase 2 governance) and retries on transient errors.
"""

from __future__ import annotations

import base64
import contextlib
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
# A dedicated vision-language model for document understanding. History:
# google/diffusiongemma-* is an image *generation* model and cannot read
# documents; the *-omni-*-reasoning models burn the token budget on
# reasoning_content; nvidia/nemotron-nano-12b-v2-vl went unhealthy on the
# shared endpoint (persistent HTTP 500 "EngineCore encountered an issue").
# meta/llama-3.2-11b-vision-instruct is stable there — but accepts at most ONE
# image per request, hence DEFAULT_MAX_IMAGES below.
DEFAULT_MODEL = "meta/llama-3.2-11b-vision-instruct"
# llama-3.2 vision rejects multi-image prompts (HTTP 400). Cap the page images
# sent to the model; raise NVIDIA_MAX_IMAGES if you move to a model that takes
# more. See extract().
DEFAULT_MAX_IMAGES = 1

# NVIDIA's shared endpoint returns these when a model's worker pool is
# saturated (503 "Worker local total request limit reached") or briefly
# unhealthy (500/502/504) — worth retrying with backoff.
_RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
# These indicate a bad request / credentials / unknown model and will never
# succeed on retry — fail fast and surface the response body.
_PERMANENT_STATUS = frozenset({400, 401, 403, 404, 405, 422})


def _env_int(name: str, default: int) -> int:
    """Read a non-negative int from the environment, falling back on default."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r (want int); using default %d", name, raw, default)
        return default


class NvidiaGateway:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        max_images: int | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.model = model or (os.getenv("NVIDIA_MODEL") or DEFAULT_MODEL)
        base = base_url or (os.getenv("NVIDIA_BASE_URL") or DEFAULT_BASE_URL)
        self.base_url = base.rstrip("/")
        # Interactive-friendly and env-tunable. The upload path falls back to
        # regex on VLM failure, so a bounded budget (default ~3x60s) beats the
        # old 5x120s, which made every upload hang for minutes during an outage.
        self.timeout = timeout if timeout is not None else _env_int("NVIDIA_TIMEOUT", 60)
        self.max_retries = (
            max_retries if max_retries is not None else _env_int("NVIDIA_MAX_RETRIES", 2)
        )
        self.max_images = (
            max_images
            if max_images is not None
            else _env_int("NVIDIA_MAX_IMAGES", DEFAULT_MAX_IMAGES)
        )

    def extract(
        self,
        images: list[bytes],
        prompt: str,
        tenant_id: str,
        pii_classes: list[str] | None = None,
        response_schema: dict[str, Any] | None = None,
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
        response_schema : dict | None
            When set, request NVIDIA NIM guided decoding by attaching the JSON
            Schema as ``nvext.guided_json`` so the model is constrained to emit
            conforming JSON. Not all hosted models honour it; callers that need
            a guarantee should validate the reply and fall back on rejection
            (see ``audit_v2.gateway.structured.extract_structured``).

        Returns
        -------
        ModelResponse
            Parsed content string and token usage metadata.
        """
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY environment variable or api_key parameter is required")

        # Cap page images to what the model accepts. llama-3.2 vision rejects
        # multi-image prompts (HTTP 400); rather than fail the whole document,
        # send the first max_images page(s) and log the dropped ones so the
        # truncation is visible, not silent.
        if self.max_images and len(images) > self.max_images:
            logger.warning(
                "Document has %d page images but model %s accepts %d; sending the "
                "first %d for tenant %s. Remaining %d page(s) not seen by the VLM.",
                len(images),
                self.model,
                self.max_images,
                self.max_images,
                tenant_id,
                len(images) - self.max_images,
            )
            images = images[: self.max_images]

        # PHASES_V2 §4 Phase 2: Redact PII in text prompt before model call
        clean_prompt = redact(prompt, pii_classes=pii_classes)

        # Base64 encode images for data URL content parts
        content_parts: list[dict[str, Any]] = [{"type": "text", "text": clean_prompt}]
        for img_bytes in images:
            b64_str = base64.b64encode(img_bytes).decode("utf-8")
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"},
                }
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": content_parts}],
            "max_tokens": 4096,
            "temperature": 0.1,
            "stream": False,
        }
        if response_schema is not None:
            # NVIDIA NIM guided decoding: constrain the completion to the schema.
            payload["nvext"] = {"guided_json": response_schema}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"
        start_time = time.monotonic()
        attempt = 0
        last_error: Exception | None = None
        max_attempts = self.max_retries + 1

        while attempt < max_attempts:
            attempt += 1
            logger.info(
                "NvidiaGateway call attempt %d/%d for tenant %s (%d page images, model=%s)",
                attempt,
                max_attempts,
                tenant_id,
                len(images),
                self.model,
            )
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as err:
                # Network hiccup / read timeout — transient, retry.
                last_error = err
                logger.warning(
                    "NvidiaGateway attempt %d/%d network error for tenant %s: %s",
                    attempt,
                    max_attempts,
                    tenant_id,
                    err,
                )
                self._backoff(attempt, max_attempts, None)
                continue

            # Fail fast on client / credential / unknown-model errors.
            if resp.status_code in _PERMANENT_STATUS:
                raise RuntimeError(
                    f"NvidiaGateway request rejected (HTTP {resp.status_code}) "
                    f"for model '{self.model}': {resp.text[:500]}"
                )

            # Retry on worker saturation / transient server errors.
            if resp.status_code in _RETRYABLE_STATUS:
                last_error = requests.HTTPError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                logger.warning(
                    "NvidiaGateway attempt %d/%d transient HTTP %d for tenant %s: %s",
                    attempt,
                    max_attempts,
                    resp.status_code,
                    tenant_id,
                    resp.text[:200],
                )
                # On final primary retry attempt, swap to fallback model pool if available
                default_fallback = (
                    "meta/llama-3.2-90b-vision-instruct"
                    if images
                    else "meta/llama-3.3-70b-instruct"
                )
                fallback = os.getenv("NVIDIA_FALLBACK_MODEL", default_fallback)
                if attempt == max_attempts and self.model != fallback:
                    logger.warning(
                        "Primary model %s pool exhausted/unhealthy; "
                        "retrying once with fallback model %s",
                        self.model,
                        fallback,
                    )
                    payload["model"] = fallback
                    max_attempts += 1
                self._backoff(attempt, max_attempts, resp.headers.get("Retry-After"))
                continue

            # Any other non-2xx: surface it directly.
            if not resp.ok:
                raise RuntimeError(
                    f"NvidiaGateway HTTP {resp.status_code} for model "
                    f"'{self.model}': {resp.text[:500]}"
                )

            # 2xx — parse the completion; a malformed/truncated body is retryable.
            try:
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise ValueError(f"No choices in response: {str(data)[:300]}")
                content = choices[0].get("message", {}).get("content")
                if not content:
                    # A few reasoning models put a final answer in
                    # reasoning_content. Accept that field only when it is a
                    # complete JSON value; chain-of-thought prose is never
                    # exposed to downstream parsers.
                    reasoning = choices[0].get("message", {}).get("reasoning_content")
                    if reasoning:
                        stripped = reasoning.strip()
                        try:
                            json.loads(stripped)
                        except json.JSONDecodeError as err:
                            raise RuntimeError(
                                "NVIDIA model returned reasoning but no final content"
                            ) from err
                        content = stripped
                    else:
                        raise RuntimeError("NVIDIA model returned no final content")
                usage = data.get("usage", {})
                return ModelResponse(
                    content=content,
                    model_version=data.get("model", self.model),
                    tokens_prompt=usage.get("prompt_tokens", 0),
                    tokens_completion=usage.get("completion_tokens", 0),
                    latency_ms=(time.monotonic() - start_time) * 1000,
                )
            except (KeyError, IndexError, ValueError, json.JSONDecodeError) as err:
                last_error = err
                logger.warning(
                    "NvidiaGateway attempt %d/%d bad response for tenant %s: %s",
                    attempt,
                    max_attempts,
                    tenant_id,
                    err,
                )
                self._backoff(attempt, max_attempts, None)
                continue

        raise RuntimeError(
            f"NvidiaGateway failed after {max_attempts} attempts for model "
            f"'{self.model}': {last_error}"
        ) from last_error

    def _backoff(self, attempt: int, max_attempts: int, retry_after: str | None) -> None:
        """Sleep between retries (capped exponential); no-op after the last attempt."""
        if attempt >= max_attempts:
            return
        delay = float(min(2**attempt, 30))
        if retry_after:
            with contextlib.suppress(TypeError, ValueError):
                delay = float(retry_after)
        time.sleep(delay)
