"""Local Qwen2.5-VL gateway for Ollama's native chat API."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from io import BytesIO
from typing import Any

import requests
from PIL import Image

from audit_v2.gateway.vlm_gateway import ModelResponse

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5vl:3b"
TRANSCRIPTION_PROMPT = (
    "Transcribe every visible word and table value in this document exactly. "
    "Preserve reading order and table relationships. Do not calculate, infer, "
    "correct, or summarize anything."
)
_INFERENCE_SLOT = threading.Semaphore(1)
_CACHE_LOCK = threading.Lock()
_TRANSCRIPT_CACHE: OrderedDict[str, tuple[float, str, str]] = OrderedDict()


def clear_transcript_cache() -> None:
    """Clear cached Qwen page transcriptions."""
    with _CACHE_LOCK:
        _TRANSCRIPT_CACHE.clear()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _prepare_image(image: bytes) -> bytes:
    """Bound visual tokens for the 4K context while preserving the 200-DPI source."""
    max_edge = max(512, _env_int("QWEN_VL_MAX_IMAGE_EDGE", 1200))
    try:
        with Image.open(BytesIO(image)) as opened:
            if max(opened.size) <= max_edge:
                return image
            resized = opened.convert("RGB")
            resized.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            output = BytesIO()
            resized.save(output, format="JPEG", quality=90, optimize=True)
            return output.getvalue()
    except Exception:
        # Tests and callers may provide opaque image bytes. Let Ollama produce
        # the authoritative decoding error rather than hiding it here.
        return image


class QwenVlGateway:
    """Deterministic local vision requests through Ollama."""

    backend = "qwen_ollama"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.base_url = (base_url or (os.getenv("QWEN_VL_BASE_URL") or DEFAULT_BASE_URL)).rstrip(
            "/"
        )
        self.model = model or (os.getenv("QWEN_VL_MODEL") or DEFAULT_MODEL)
        self.timeout = timeout if timeout is not None else _env_int("QWEN_VL_TIMEOUT", 120)
        self.max_retries = (
            max_retries if max_retries is not None else _env_int("QWEN_VL_MAX_RETRIES", 1)
        )
        self.transcription_max_tokens = _env_int("QWEN_VL_TRANSCRIPTION_MAX_TOKENS", 4096)
        self.structured_max_tokens = _env_int("QWEN_VL_STRUCTURED_MAX_TOKENS", 1536)
        self.context_length = _env_int("QWEN_VL_CONTEXT_LENGTH", 4096)
        self.network_call_count = 0
        self.last_cache_hit = False

    def health(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            response.raise_for_status()
            models = [
                str(item.get("name") or item.get("model"))
                for item in response.json().get("models", [])
            ]
            return {
                "available": self.model in models,
                "base_url": self.base_url,
                "configured_model": self.model,
                "loaded_models": models,
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
            max_tokens=self.transcription_max_tokens,
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
        del pii_classes
        if len(images) != 1:
            raise ValueError("Qwen page extraction requires exactly one image")

        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64.b64encode(_prepare_image(images[0])).decode("ascii")],
                }
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.00001,
                "top_k": 1,
                "num_ctx": self.context_length,
                "num_predict": max_tokens,
            },
        }
        if response_schema is not None:
            payload["format"] = response_schema

        last_error: Exception | None = None
        started = time.monotonic()
        with _INFERENCE_SLOT:
            for attempt in range(self.max_retries + 1):
                try:
                    self.network_call_count += 1
                    response = requests.post(
                        f"{self.base_url}/api/chat", json=payload, timeout=self.timeout
                    )
                    if not response.ok:
                        detail = response.text.strip().replace("\n", " ")[:500]
                        raise RuntimeError(
                            f"Ollama HTTP {response.status_code}: {detail or 'no response body'}"
                        )
                    data = response.json()
                    content = data["message"].get("content")
                    if not content:
                        raise ValueError("Qwen returned empty content")
                    if data.get("done_reason") == "length":
                        raise ValueError("Qwen response was truncated by the context/output limit")
                    return ModelResponse(
                        content=str(content),
                        model_version=str(data.get("model", self.model)),
                        tokens_prompt=int(data.get("prompt_eval_count", 0)),
                        tokens_completion=int(data.get("eval_count", 0)),
                        latency_ms=(time.monotonic() - started) * 1000,
                    )
                except (
                    requests.RequestException,
                    KeyError,
                    RuntimeError,
                    ValueError,
                ) as exc:
                    last_error = exc
                    logger.warning(
                        "Qwen attempt %d/%d failed for tenant %s: %s",
                        attempt + 1,
                        self.max_retries + 1,
                        tenant_id,
                        exc,
                    )
                    if attempt < self.max_retries:
                        time.sleep(min(2**attempt, 2))
        raise RuntimeError(f"Qwen failed after {self.max_retries + 1} attempt(s): {last_error}")

    def transcribe(self, image: bytes, tenant_id: str) -> ModelResponse:
        ttl = _env_int("QWEN_VL_CACHE_TTL_SECONDS", 3600)
        capacity = max(1, _env_int("QWEN_VL_CACHE_MAX_PAGES", 256))
        prompt_version = os.getenv("QWEN_VL_TRANSCRIPT_PROMPT_VERSION", "exact-transcription-v1")
        key = hashlib.sha256(
            b"\0".join(
                (
                    tenant_id.encode(),
                    self.base_url.encode(),
                    self.model.encode(),
                    prompt_version.encode(),
                    image,
                )
            )
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
            TRANSCRIPTION_PROMPT,
            tenant_id,
            max_tokens=self.transcription_max_tokens,
        )
        stored_at = time.monotonic()
        with _CACHE_LOCK:
            _TRANSCRIPT_CACHE[key] = (
                stored_at,
                response.content,
                response.model_version,
            )
            _TRANSCRIPT_CACHE.move_to_end(key)
            while len(_TRANSCRIPT_CACHE) > capacity:
                _TRANSCRIPT_CACHE.popitem(last=False)
        return response
