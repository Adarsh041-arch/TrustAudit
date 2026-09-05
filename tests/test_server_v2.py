"""Contract and integration tests for FastAPI server_v2.py on port :8100."""

import io
import zipfile
from io import BytesIO
from pathlib import Path
from fastapi.testclient import TestClient
import fitz
from audit_v2.server import app, DOCUMENTS_STORE, FINDINGS_STORE, AUDIT_LOG

client = TestClient(app)


def _make_sample_pdf() -> bytes:
    sample = Path(__file__).parent.parent / "sample_docs" / "Commercial_Invoice_INV-2026-453.pdf"
    if sample.exists():
        return sample.read_bytes()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "INVOICE #INV-2026-0715\nVendor: NewTech Solutions\nTotal: $1,250.00\nDate: 2026-07-15\nItem: Server License Qty: 1 Price: $1250.00")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


MINIMAL_PDF = _make_sample_pdf()


class TestServerV2:
    def test_health_check(self):
        res = client.get("/api/v2/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "OK"
        assert body["version"] == "2.0.0"
        assert body["audit_log_valid"] is True
        assert body["extraction_policy"]["mode"] == "balanced"
        assert body["extraction_policy"]["transcription_max_tokens"] == 4096

    def test_upload_document_text_pdf(self):
        sample = Path(__file__).parent.parent / "sample_docs" / "INV-2026-0715_NewTech_Solutions.pdf"
        pdf_bytes = sample.read_bytes() if sample.exists() else MINIMAL_PDF
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
        sample = Path(__file__).parent.parent / "sample_docs" / "INV-2026-0715_NewTech_Solutions.pdf"
        pdf_bytes = sample.read_bytes() if sample.exists() else MINIMAL_PDF
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
        sample = Path(__file__).parent.parent / "sample_docs" / "Commercial_Invoice_INV-2026-453.pdf"
        pdf_bytes = sample.read_bytes() if sample.exists() else MINIMAL_PDF


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
        # Per-document interval is a band around the document's OWN score
        # (n=1 -> ±12.5, clamped), NOT the batch-mean CI reused on every card.
        pi = dr["prediction_interval"]
        assert pi["lower"] == max(0.0, dr["score"] - 12.5)
        assert pi["upper"] == min(100.0, dr["score"] + 12.5)
        assert pi["lower"] <= dr["score"] <= pi["upper"]
        assert body["analytics"]["kpis"]["total_audited"] == 1
        assert len(body["analytics"]["charts"]["risk_distribution"]) == 1


def test_eval_endpoint_returns_eight_metric_grid():
    with TestClient(app) as client:
        res = client.get("/api/v2/audit/eval")
    assert res.status_code == 200
    metrics = res.json()["metrics"]
    for key in ("accuracy", "precision", "recall", "f1_score", "false_positive_rate",
                "false_negative_rate", "average_latency_seconds", "average_confidence_score"):
        assert key in metrics
    assert metrics["precision"] == 1.0  # golden-set overall precision


def test_report_endpoint_returns_docx_and_pdf():
    payload = {
        "documents": [{
            "document_name": "inv.pdf", "document_type": "invoice", "passed": False,
            "score": 60.0, "risk_level": "Medium Risk", "risk_explanation": "x",
            "summary_text": "Validated document summary marker.",
            "confidence_score": 60.0, "human_review_recommended": False,
            "ml_prediction": {"prediction": "Partially Compliant", "probabilities": {"compliant": 15.0, "partially_compliant": 70.0, "non_compliant": 15.0}, "mode": "Rule-based (V2)"},
            "failed_rules": [], "preview_base64": "", "page_count": 1,
        }],
        "findings": [],
        "audit_title": "T",
        "executive_summary": "Executive batch summary marker.",
    }
    with TestClient(app) as client:
        docx = client.post("/api/v2/audit/report?format=docx", json=payload)
        pdf = client.post("/api/v2/audit/report?format=pdf", json=payload)
        bad = client.post("/api/v2/audit/report?format=xlsx", json=payload)
    assert docx.status_code == 200 and docx.content[:4] == b"PK\x03\x04"
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert bad.status_code == 400
    with zipfile.ZipFile(BytesIO(docx.content)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "Executive batch summary marker." in document_xml
    assert "Validated document summary marker." in document_xml
    with fitz.open(stream=pdf.content, filetype="pdf") as report_pdf:
        pdf_text = "\n".join(page.get_text() for page in report_pdf)
    assert "Executive batch summary marker." in pdf_text
    assert "Validated document summary marker." in pdf_text


# ─── Evidence-based pipeline (new_requirements.md §5–§8, plan §8) ─────────────

_VALID_NATURES = {
    "metadata", "extracted_fields", "arithmetic_computation",
    "vlm_observations", "ocr+regex_observations",
}


def test_upload_response_carries_evidences_and_contradictions():
    """Each document_result carries an ordered evidence trail + contradictions."""
    sample = Path(__file__).parent.parent / "sample_docs" / "Commercial_Invoice_INV-2026-453.pdf"
    pdf_bytes = sample.read_bytes() if sample.exists() else MINIMAL_PDF

    with TestClient(app) as client:
        res = client.post(
            "/api/v2/audit/upload?tenant_id=tenant_default",
            files={"files": ("invoice.pdf", BytesIO(pdf_bytes), "application/pdf")},
        )
    assert res.status_code == 200
    dr = res.json()["document_results"][0]

    assert isinstance(dr["evidences"], list) and dr["evidences"]
    assert isinstance(dr["contradictions"], list)
    natures = {e["nature"] for e in dr["evidences"]}
    assert natures <= _VALID_NATURES
    sources = [e["source"] for e in dr["evidences"]]
    # Offline (no key): regex + OCR + arithmetic + metadata; VLM skipped.
    assert "regex" in sources and "rapidocr" in sources
    assert "arithmetic_computation" in natures
    # metadata evidence is always last.
    assert dr["evidences"][-1]["nature"] == "metadata"
    # No key → the LLM cross-check is skipped, so no contradictions.
    assert dr["contradictions"] == []


def _inconsistent_invoice(doc_id: str):
    """An invoice whose line total (999) ≠ qty×price (2×100) → arithmetic FAIL."""
    from audit_v2.domain.models import (
        Coverage,
        DocumentHeader,
        DocumentType,
        ExtractedDocument,
        LineItem,
        ProvenancedValue,
    )

    def pv(v, cur=None):
        return ProvenancedValue(value=v, raw=v, page=1, confidence=0.99, currency=cur)

    li = LineItem(
        line_number=1, description=pv("Widget"), quantity=pv("2"),
        unit_price=pv("100.00", "USD"), line_total=pv("999.00", "USD"),
    )
    return ExtractedDocument(
        document_id=doc_id, tenant_id="t", doc_type=DocumentType.INVOICE,
        header=DocumentHeader(
            document_id=doc_id, doc_type=DocumentType.INVOICE, grand_total=pv("999.00", "USD"),
        ),
        line_items=[li],
        coverage=Coverage(pages_total=1, pages_examined=1, coverage_complete=True),
        page_count=1, extractor_version="test",
    )


def test_deterministic_arith_fail_authoritative_and_not_softened():
    """A deterministic arithmetic FAIL keeps its penalty; an overlapping LLM
    contradiction is dropped (deterministic authority, new_requirements.md §5)."""
    from datetime import date

    from audit_v2 import server
    from audit_v2.analytics.risk_scorer import compute_document_score
    from audit_v2.domain.evidence import Contradiction, EvidenceNature
    from audit_v2.domain.finding_generator import make_finding_from_result
    from audit_v2.domain.models import CheckDeterminism, FindingStatus, Severity

    doc = _inconsistent_invoice("doc_arith")
    included = [
        c.check_id for c in server.CATALOG.checks
        if doc.doc_type in c.applies_to and c.determinism == CheckDeterminism.DETERMINISTIC
    ]
    results = server.CHECK_RUNNER.run_all(
        document=doc, included_check_ids=included, skipped_check_ids={},
        current_date=date.today(),
    )
    fails = [r for r in results if r.status == FindingStatus.FAIL]
    assert any(r.check_id == "CHK-ARITH-LINE-001" for r in fails)

    det_findings = [
        make_finding_from_result(
            result=r, check_entry=server.CATALOG_BY_ID[r.check_id], document=doc,
            ruleset_version=server.RULESET_VERSION, prompt_version=server.PROMPT_VERSION,
            model_version=server.MODEL_VERSION,
        )
        for r in fails
    ]
    det_fails = [f for f in det_findings if f.status == FindingStatus.FAIL]

    arith_c = Contradiction(
        document_id=doc.document_id, nature=EvidenceNature.ARITHMETIC_COMPUTATION,
        evidence="line total off", reason="r", severity=Severity.CRITICAL,
    )
    # The LLM contradiction overlaps the deterministic FAIL → dropped in the server.
    assert server._contradiction_overlaps_fail(arith_c, det_fails) is True
    # The deterministic FAIL stands and penalises the score.
    assert compute_document_score(det_findings) < 100.0
    # And even if surfaced, a contradiction is only ever advisory, never a FAIL.
    cf = server._contradiction_to_finding(arith_c, doc, "t", 0)
    assert cf.status == FindingStatus.NEEDS_REVIEW


def test_score_reflects_contradiction_finding():
    """A (non-overlapping) contradiction lowers the document score (§7)."""
    from audit_v2 import server
    from audit_v2.analytics.risk_scorer import compute_document_score
    from audit_v2.domain.evidence import Contradiction, EvidenceNature
    from audit_v2.domain.models import Severity

    doc = _inconsistent_invoice("doc_score")  # reused only for its id/type
    c = Contradiction(
        document_id=doc.document_id, nature=EvidenceNature.VLM_OBSERVATIONS,
        evidence="e", reason="r", severity=Severity.HIGH,
    )
    cf = server._contradiction_to_finding(c, doc, "t", 0)
    assert compute_document_score([cf]) < compute_document_score([])
