"""Local GLM-OCR gateway for llama.cpp's OpenAI-compatible server."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any

import requests

from audit_v2.gateway.vlm_gateway import ModelResponse

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_MODEL = "models/GLM-OCR-Q8_0.gguf"
_INFERENCE_SLOT = threading.Semaphore(1)
_CACHE_LOCK = threading.Lock()
_TRANSCRIPT_CACHE: OrderedDict[str, tuple[float, str, str]] = OrderedDict()


def clear_transcript_cache() -> None:
    """Clear cached page transcriptions (primarily for tests and operations)."""
    with _CACHE_LOCK:
        _TRANSCRIPT_CACHE.clear()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


class GlmOcrGateway:
    """Deterministic local OCR requests with one bounded retry by default."""

    backend = "glm_ocr"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.base_url = (base_url or (os.getenv("GLM_OCR_BASE_URL") or DEFAULT_BASE_URL)).rstrip(
            "/"
        )
        self.model = model or (os.getenv("GLM_OCR_MODEL") or DEFAULT_MODEL)
        self.timeout = timeout if timeout is not None else _env_int("GLM_OCR_TIMEOUT", 120)
        self.max_retries = (
            max_retries if max_retries is not None else _env_int("GLM_OCR_MAX_RETRIES", 1)
        )
        self.network_call_count = 0
        self.last_cache_hit = False
        self.transcription_max_tokens = _env_int("GLM_OCR_TRANSCRIPTION_MAX_TOKENS", 4096)
        self.structured_max_tokens = _env_int("GLM_OCR_STRUCTURED_MAX_TOKENS", 1536)

    def health(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.base_url}/models", timeout=2)
            response.raise_for_status()
            data = response.json()
            model_ids = [item.get("id") for item in data.get("data", [])]
            return {
                "available": self.model in model_ids or bool(model_ids),
                "base_url": self.base_url,
                "configured_model": self.model,
                "loaded_models": model_ids,
            }
        except Exception as exc:
            return {
                "available": False,
                "base_url": self.base_url,
                "configured_model": self.model,
                "loaded_models": [],
                "error": str(exc),
            }

    def extract(
        self,
        images: list[bytes],
        prompt: str,
        tenant_id: str,
        pii_classes: list[str] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> ModelResponse:
        return self.extract_limited(
            images,
            prompt,
            tenant_id,
            pii_classes,
            response_schema,
            max_tokens=_env_int("GLM_OCR_TRANSCRIPTION_MAX_TOKENS", 4096),
        )

    def extract_limited(
        self,
        images: list[bytes],
        prompt: str,
        tenant_id: str,
        pii_classes: list[str] | None = None,
        response_schema: dict[str, Any] | None = None,
        *,
        max_tokens: int,
    ) -> ModelResponse:
        del pii_classes  # local inference; no prompt leaves the host
        if len(images) != 1:
            raise ValueError("GLM-OCR page extraction requires exactly one image")

        image = base64.b64encode(images[0]).decode("ascii")
        content: list[dict[str, Any]] = [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
            {"type": "text", "text": prompt},
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "top_p": 0.00001,
            "top_k": 1,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "document_extraction",
                    "strict": True,
                    "schema": response_schema,
                },
            }

        last_error: Exception | None = None
        started = time.monotonic()
        with _INFERENCE_SLOT:
            for attempt in range(self.max_retries + 1):
                try:
                    self.network_call_count += 1
                    response = requests.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        timeout=self.timeout,
                    )
                    response.raise_for_status()
                    data = response.json()
                    message = data["choices"][0]["message"].get("content")
                    if not message:
                        raise ValueError("GLM-OCR returned empty content")
                    usage = data.get("usage", {})
                    return ModelResponse(
                        content=str(message),
                        model_version=str(data.get("model", self.model)),
                        tokens_prompt=int(usage.get("prompt_tokens", 0)),
                        tokens_completion=int(usage.get("completion_tokens", 0)),
                        latency_ms=(time.monotonic() - started) * 1000,
                    )
                except (
                    requests.RequestException,
                    KeyError,
                    IndexError,
                    ValueError,
                    json.JSONDecodeError,
                ) as exc:
                    last_error = exc
                    logger.warning(
                        "GLM-OCR attempt %d/%d failed for tenant %s: %s",
                        attempt + 1,
                        self.max_retries + 1,
                        tenant_id,
                        exc,
                    )
                    if attempt < self.max_retries:
                        time.sleep(min(2**attempt, 2))
        raise RuntimeError(f"GLM-OCR failed after {self.max_retries + 1} attempt(s): {last_error}")

    def transcribe(self, image: bytes, tenant_id: str) -> ModelResponse:
        ttl = _env_int("GLM_OCR_CACHE_TTL_SECONDS", 3600)
        capacity = max(1, _env_int("GLM_OCR_CACHE_MAX_PAGES", 256))
        prompt_version = os.getenv("GLM_OCR_TRANSCRIPT_PROMPT_VERSION", "text-recognition-v1")
        key = hashlib.sha256(
            b"\0".join((tenant_id.encode(), self.model.encode(), prompt_version.encode(), image))
        ).hexdigest()
        now = time.monotonic()
        with _CACHE_LOCK:
            cached = _TRANSCRIPT_CACHE.get(key)
            if cached and now - cached[0] <= ttl:
                _TRANSCRIPT_CACHE.move_to_end(key)
                self.last_cache_hit = True
                return ModelResponse(content=cached[1], model_version=cached[2], latency_ms=0.0)
            if cached:
                _TRANSCRIPT_CACHE.pop(key, None)
        self.last_cache_hit = False
        response = self.extract_limited(
            [image],
            "Text Recognition:",
            tenant_id,
            max_tokens=_env_int("GLM_OCR_TRANSCRIPTION_MAX_TOKENS", 4096),
        )
        with _CACHE_LOCK:
            _TRANSCRIPT_CACHE[key] = (now, response.content, response.model_version)
            _TRANSCRIPT_CACHE.move_to_end(key)
            while len(_TRANSCRIPT_CACHE) > capacity:
                _TRANSCRIPT_CACHE.popitem(last=False)
        return response
