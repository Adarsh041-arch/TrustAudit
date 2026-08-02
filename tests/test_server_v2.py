"""Contract and integration tests for FastAPI server_v2.py on port :8100."""

import io
from fastapi.testclient import TestClient
from backend.server_v2 import app, DOCUMENTS_STORE, FINDINGS_STORE, AUDIT_LOG

client = TestClient(app)


class TestServerV2:
    def test_health_check(self):
        res = client.get("/api/v2/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "OK"
        assert body["version"] == "2.0.0"
        assert body["audit_log_valid"] is True

    def test_upload_document_text_pdf(self):
        with open("sample_docs/INV-2026-0715_NewTech_Solutions.pdf", "rb") as f:
            pdf_bytes = f.read()
        res = client.post(
            "/api/v2/audit/upload",
            files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
        )
        assert res.status_code == 200
        body = res.json()
        assert "document" in body
        assert "is_vlm_fallback" in body


    def test_audit_log_endpoint(self):
        res = client.get("/api/v2/audit/log")
        assert res.status_code == 200
        body = res.json()
        assert body["chain_valid"] is True
        assert isinstance(body["entries"], list)

    def test_findings_endpoint(self):
        res = client.get("/api/v2/audit/findings")
        assert res.status_code == 200
        body = res.json()
        assert "findings" in body

    def test_review_queue_endpoint(self):
        res = client.get("/api/v2/audit/review-queue")
        assert res.status_code == 200
        body = res.json()
        assert "pending_items" in body
