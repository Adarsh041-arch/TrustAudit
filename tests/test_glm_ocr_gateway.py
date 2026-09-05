"""Contract tests for the local llama.cpp GLM-OCR gateway."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

from audit_v2.gateway.glm_ocr_gateway import GlmOcrGateway, clear_transcript_cache


@pytest.fixture(autouse=True)
def _empty_transcript_cache() -> None:
    clear_transcript_cache()


class _Response:
    def __init__(self, data: dict, status: int = 200) -> None:
        self._data = data
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self) -> dict:
        return self._data


def test_schema_and_deterministic_sampling_are_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict = {}

    def post(url: str, *, json: dict, timeout: int) -> _Response:
        sent.update(url=url, payload=json, timeout=timeout)
        return _Response({
            "model": "loaded-glm",
            "choices": [{"message": {"content": '{"invoice_number":"INV-1"}'}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        })

    monkeypatch.setattr("audit_v2.gateway.glm_ocr_gateway.requests.post", post)
    schema = {"type": "object", "properties": {"invoice_number": {"type": "string"}}}
    gateway = GlmOcrGateway(base_url="http://local/v1", model="glm", timeout=120)
    result = gateway.extract([b"jpeg"], "extract", "tenant", response_schema=schema)

    payload = sent["payload"]
    assert sent["url"] == "http://local/v1/chat/completions"
    assert sent["timeout"] == 120
    assert payload["temperature"] == 0
    assert payload["top_p"] == 0.00001
    assert payload["top_k"] == 1
    assert payload["max_tokens"] == 4096
    assert payload["response_format"]["json_schema"]["schema"] == schema
    assert result.model_version == "loaded-glm"


def test_malformed_response_retries_once(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = iter([_Response({"choices": []}), _Response({
        "choices": [{"message": {"content": "recognized"}}],
    })])
    calls = 0

    def post(*args, **kwargs) -> _Response:
        nonlocal calls
        calls += 1
        return next(replies)

    monkeypatch.setattr("audit_v2.gateway.glm_ocr_gateway.requests.post", post)
    monkeypatch.setattr("audit_v2.gateway.glm_ocr_gateway.time.sleep", lambda _: None)
    result = GlmOcrGateway(max_retries=1).transcribe(b"jpeg", "tenant")

    assert result.content == "recognized"
    assert calls == 2


def test_server_unavailability_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(*args, **kwargs):
        raise requests.Timeout("offline")

    monkeypatch.setattr("audit_v2.gateway.glm_ocr_gateway.requests.post", post)
    monkeypatch.setattr("audit_v2.gateway.glm_ocr_gateway.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="after 2 attempt"):
        GlmOcrGateway(max_retries=1).transcribe(b"jpeg", "tenant")


def test_health_reports_loaded_model_and_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "audit_v2.gateway.glm_ocr_gateway.requests.get",
        lambda *a, **k: _Response({"data": [{"id": "glm"}]}),
    )
    assert GlmOcrGateway(model="glm").health()["available"] is True

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr("audit_v2.gateway.glm_ocr_gateway.requests.get", unavailable)
    health = GlmOcrGateway(model="glm").health()
    assert health["available"] is False
    assert "offline" in health["error"]


def test_page_gateway_rejects_multi_image_request() -> None:
    with pytest.raises(ValueError, match="exactly one image"):
        GlmOcrGateway().extract([b"one", b"two"], "extract", "tenant")


def test_transcript_cache_is_tenant_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def post(*args, **kwargs) -> _Response:
        nonlocal calls
        calls += 1
        return _Response({"choices": [{"message": {"content": "Invoice"}}]})

    monkeypatch.setattr("audit_v2.gateway.glm_ocr_gateway.requests.post", post)
    gateway = GlmOcrGateway(max_retries=0)
    gateway.transcribe(b"same-page", "tenant-a")
    gateway.transcribe(b"same-page", "tenant-a")
    assert gateway.last_cache_hit is True
    gateway.transcribe(b"same-page", "tenant-b")
    assert calls == 2


def test_gpu_inference_is_process_wide_serialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = 0
    maximum = 0
    guard = threading.Lock()

    def post(*args, **kwargs) -> _Response:
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        with guard:
            active -= 1
        return _Response({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr("audit_v2.gateway.glm_ocr_gateway.requests.post", post)
    gateways = [GlmOcrGateway(max_retries=0), GlmOcrGateway(max_retries=0)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(
            lambda pair: pair[0].extract([b"page"], "read", pair[1]),
            zip(gateways, ("tenant-a", "tenant-b"), strict=True),
        ))
    assert maximum == 1
