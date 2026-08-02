"""Unit tests for NvidiaGateway (PHASES_V2 §4 Phase 5.1)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

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

    @patch("audit_v2.gateway.nvidia_gateway.requests.post")
    def test_retry_on_failure(self, mock_post):
        mock_err = MagicMock()
        mock_err.raise_for_status.side_effect = requests.RequestException("API timeout")
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {"choices": [{"message": {"content": "{}"}}]}

        # Fail once, then succeed
        mock_post.side_effect = [mock_err, mock_ok]

        gw = NvidiaGateway(api_key="test-key", max_retries=1)
        res = gw.extract(images=[b"img"], prompt="Extract", tenant_id="t1")
        assert res.content == "{}"
        assert mock_post.call_count == 2
