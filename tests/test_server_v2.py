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
            files=[("files", ("invoice.pdf", pdf_bytes, "application/pdf"))],
        )
        assert res.status_code == 200
        body = res.json()
        assert "documents" in body
        assert body["count"] >= 1
        assert "is_vlm_fallback" in body

    def test_upload_multi_document_batch(self):
        with open("sample_docs/INV-2026-0715_NewTech_Solutions.pdf", "rb") as f:
            pdf_bytes = f.read()
        res = client.post(
            "/api/v2/audit/upload",
            files=[
                ("files", ("invoice1.pdf", pdf_bytes, "application/pdf")),
                ("files", ("invoice2.pdf", pdf_bytes, "application/pdf")),
            ],
        )
        assert res.status_code == 200
        body = res.json()
        assert body["count"] == 2
        assert len(body["documents"]) == 2



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

    def test_upload_response_has_enriched_document_results(self):
        from io import BytesIO

        with open("sample_docs/INV-2026-0715_NewTech_Solutions.pdf", "rb") as f:
            pdf_bytes = f.read()

        with TestClient(app) as client:
            res = client.post(
                "/api/v2/audit/upload?tenant_id=tenant_default",
                files={"files": ("invoice.pdf", BytesIO(pdf_bytes), "application/pdf")},
            )
        assert res.status_code == 200
        body = res.json()
        assert len(body["document_results"]) == 1
        dr = body["document_results"][0]
        assert dr["document_name"] == "invoice.pdf"
        assert dr["document_type"] in {"invoice", "purchase_order", "delivery_challan", "goods_receipt_note", "contract", "letter"}
        assert 0.0 <= dr["score"] <= 100.0
        assert dr["risk_level"] in {"Low Risk", "Medium Risk", "High Risk"}
        assert "ml_prediction" in dr and dr["ml_prediction"]["mode"] == "Rule-based (V2)"
        assert dr["preview_base64"] != ""
        assert "lower" in body["prediction_interval"] and "upper" in body["prediction_interval"]
        assert body["analytics"]["kpis"]["total_audited"] == 1
        assert len(body["analytics"]["charts"]["risk_distribution"]) == 1
