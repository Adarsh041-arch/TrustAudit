"""Unit tests for NvidiaGateway (PHASES_V2 §4 Phase 5.1)."""
from unittest.mock import MagicMock, patch

import pytest

from audit_v2.gateway.nvidia_gateway import DEFAULT_MODEL, NvidiaGateway


class TestNvidiaGateway:
    def test_missing_api_key_raises_error(self, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        gw = NvidiaGateway(api_key=None)
        with pytest.raises(ValueError, match="NVIDIA_API_KEY"):
            gw.extract(images=[b"fake_image"], prompt="Extract invoice", tenant_id="t1")

    @patch("audit_v2.gateway.nvidia_gateway.requests.post")
    def test_successful_extraction(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"header": {"vendor_name": "Acme"}}'}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        mock_post.return_value = mock_resp

        gw = NvidiaGateway(api_key="test-key", model="test-model")
        res = gw.extract(images=[b"img1_bytes"], prompt="Extract invoice", tenant_id="tenant-123")

        assert res.content == '{"header": {"vendor_name": "Acme"}}'
        assert res.model_version == "test-model"
        assert res.tokens_prompt == 100
        assert res.tokens_completion == 50
        assert res.latency_ms >= 0

        # Assert payload contains image data url and redacted prompt
        assert mock_post.called
        call_kwargs = mock_post.call_args.kwargs
        payload = call_kwargs["json"]
        assert payload["model"] == "test-model"
        assert payload["messages"][0]["role"] == "user"
        content = payload["messages"][0]["content"]
        assert content[0] == {"type": "text", "text": "Extract invoice"}
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    @patch("audit_v2.gateway.nvidia_gateway.requests.post")
    def test_pii_redaction_in_prompt(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "{}"}}],
        }
        mock_post.return_value = mock_resp

        gw = NvidiaGateway(api_key="test-key")
        prompt_with_pii = "Extract for account 123456789012 and IFSC HDFC0001234"
        gw.extract(images=[b"img"], prompt=prompt_with_pii, tenant_id="t1")

        payload = mock_post.call_args.kwargs["json"]
        clean_text = payload["messages"][0]["content"][0]["text"]
        assert "123456789012" not in clean_text
        assert "HDFC0001234" not in clean_text
        assert "[REDACTED_BANK_ACCOUNT]" in clean_text
        assert "[REDACTED_IFSC]" in clean_text

    @patch("audit_v2.gateway.nvidia_gateway.time.sleep")
    @patch("audit_v2.gateway.nvidia_gateway.requests.post")
    def test_retry_on_transient_error(self, mock_post, _mock_sleep):
        # 503 (worker saturation) is transient — retry then succeed.
        mock_err = MagicMock()
        mock_err.status_code = 503
        mock_err.text = "ResourceExhausted: Worker local total request limit reached (16/16)"
        mock_err.headers = {}
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.ok = True
        mock_ok.json.return_value = {"choices": [{"message": {"content": "{}"}}]}

        mock_post.side_effect = [mock_err, mock_ok]

        gw = NvidiaGateway(api_key="test-key", max_retries=1)
        res = gw.extract(images=[b"img"], prompt="Extract", tenant_id="t1")
        assert res.content == "{}"
        assert mock_post.call_count == 2

    @patch("audit_v2.gateway.nvidia_gateway.time.sleep")
    @patch("audit_v2.gateway.nvidia_gateway.requests.post")
    def test_no_retry_on_client_error(self, mock_post, _mock_sleep):
        # 400/401/404 will never succeed on retry — fail fast, one call only.
        mock_bad = MagicMock()
        mock_bad.status_code = 404
        mock_bad.text = '{"detail": "Function not found for account ..."}'
        mock_post.return_value = mock_bad

        gw = NvidiaGateway(api_key="test-key", model="does/not-exist", max_retries=4)
        with pytest.raises(RuntimeError, match="HTTP 404"):
            gw.extract(images=[b"img"], prompt="Extract", tenant_id="t1")
        assert mock_post.call_count == 1

    def test_defaults_are_interactive_and_single_image(self, monkeypatch):
        # Env-tunable knobs fall back to interactive-friendly defaults: a bounded
        # retry budget (~3x60s) and a single image (llama-3.2 vision's limit).
        for var in ("NVIDIA_TIMEOUT", "NVIDIA_MAX_RETRIES", "NVIDIA_MAX_IMAGES"):
            monkeypatch.delenv(var, raising=False)
        gw = NvidiaGateway(api_key="k")
        assert gw.timeout == 60
        assert gw.max_retries == 2
        assert gw.max_images == 1

    @patch("audit_v2.gateway.nvidia_gateway.requests.post")
    def test_truncates_images_beyond_model_limit(self, mock_post):
        # Multi-page docs must not 400 out on a single-image model: send the
        # first page image only (the rest are logged as dropped).
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {"choices": [{"message": {"content": "{}"}}]}
        mock_post.return_value = mock_resp

        gw = NvidiaGateway(api_key="test-key", max_images=1)
        gw.extract(images=[b"page1", b"page2", b"page3"], prompt="Extract", tenant_id="t1")

        content = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
        image_parts = [p for p in content if p.get("type") == "image_url"]
        assert len(image_parts) == 1
