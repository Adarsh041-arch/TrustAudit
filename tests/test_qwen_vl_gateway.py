"""Tests for the local Ollama Qwen vision gateway."""
from __future__ import annotations

from typing import Any

import pytest
import requests

from audit_v2.gateway.qwen_vl_gateway import (
    QwenVlGateway,
    clear_transcript_cache,
)


class _Response:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = str(payload)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_transcript_cache()


def test_schema_request_uses_deterministic_ollama_options(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def post(url: str, json: dict[str, Any], timeout: int) -> _Response:
        captured.update({"url": url, "json": json, "timeout": timeout})
        return _Response({
            "model": "qwen2.5vl:3b",
            "message": {"content": '{"value":"visible"}'},
            "prompt_eval_count": 10,
            "eval_count": 5,
        })

    monkeypatch.setattr("audit_v2.gateway.qwen_vl_gateway.requests.post", post)
    gateway = QwenVlGateway(base_url="http://ollama", max_retries=0)
    response = gateway.extract_limited(
        [b"jpeg"],
        "extract",
        "tenant-a",
        response_schema={"type": "object"},
        max_tokens=512,
    )

    assert response.content == '{"value":"visible"}'
    assert captured["url"] == "http://ollama/api/chat"
    payload = captured["json"]
    assert payload["format"] == {"type": "object"}
    assert payload["options"] == {
        "temperature": 0,
        "top_p": 0.00001,
        "top_k": 1,
        "num_ctx": 4096,
        "num_predict": 512,
    }
    assert payload["messages"][0]["images"]


def test_transcript_cache_is_tenant_isolated(monkeypatch) -> None:
    calls = 0

    def post(url: str, json: dict[str, Any], timeout: int) -> _Response:
        nonlocal calls
        calls += 1
        return _Response({
            "model": "qwen2.5vl:3b",
            "message": {"content": "exact transcript"},
        })

    monkeypatch.setattr("audit_v2.gateway.qwen_vl_gateway.requests.post", post)
    gateway = QwenVlGateway(max_retries=0)

    assert gateway.transcribe(b"same", "tenant-a").content == "exact transcript"
    assert gateway.transcribe(b"same", "tenant-a").content == "exact transcript"
    assert gateway.last_cache_hit is True
    assert gateway.transcribe(b"same", "tenant-b").content == "exact transcript"
    assert calls == 2


def test_health_and_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "audit_v2.gateway.qwen_vl_gateway.requests.get",
        lambda *args, **kwargs: _Response({
            "models": [{"name": "qwen2.5vl:3b"}],
            "data": [{"id": r"C:\llama-cpp\models\Qwen3.5-4B-Q4_K_M.gguf"}],
        }),
    )
    assert QwenVlGateway().health()["available"] is True

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(
        "audit_v2.gateway.qwen_vl_gateway.requests.get", unavailable
    )
    assert QwenVlGateway().health()["available"] is False


def test_openai_compatible_llama_cpp_extraction(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def post(url: str, json: dict[str, Any], timeout: int) -> _Response:
        captured.update({"url": url, "json": json, "timeout": timeout})
        return _Response({
            "model": r"C:\llama-cpp\models\Qwen3.5-4B-Q4_K_M.gguf",
            "choices": [{"message": {"content": '{"invoice_number":"INV-123"}'}}],
            "usage": {"prompt_tokens": 25, "completion_tokens": 12},
        })

    monkeypatch.setattr("audit_v2.gateway.qwen_vl_gateway.requests.post", post)
    gateway = QwenVlGateway(base_url="http://127.0.0.1:8080/v1", max_retries=0)
    assert gateway.is_openai_compatible is True
    assert gateway.backend == "qwen_llama"

    schema = {"type": "object", "properties": {"invoice_number": {"type": "string"}}}
    response = gateway.extract_limited(
        [b"fake_jpeg_bytes"],
        "Extract invoice details",
        "tenant-llama",
        response_schema=schema,
        max_tokens=256,
    )

    assert response.content == '{"invoice_number":"INV-123"}'
    assert response.tokens_prompt == 25
    assert response.tokens_completion == 12
    assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"

    payload = captured["json"]
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 256
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert payload["response_format"]["json_schema"]["schema"] == schema
    messages = payload["messages"]
    assert len(messages) == 1
    content_items = messages[0]["content"]
    assert content_items[0]["type"] == "image_url"
    assert content_items[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert content_items[1]["type"] == "text"
    assert content_items[1]["text"] == "Extract invoice details"

