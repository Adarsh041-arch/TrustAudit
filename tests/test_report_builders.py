from io import BytesIO

from docx import Document

from audit_v2.reporting.report_builders import generate_docx_report, generate_pdf_report

PAYLOAD = {
    "audit_title": "Test Audit",
    "documents": [
        {
            "document_name": "inv.pdf", "document_type": "invoice", "passed": False,
            "score": 60.0, "risk_level": "Medium Risk", "risk_explanation": "1 medium",
            "confidence_score": 60.0, "human_review_recommended": True,
            "ml_prediction": {"prediction": "Partially Compliant",
                              "probabilities": {"compliant": 15.0, "partially_compliant": 70.0, "non_compliant": 15.0},
                              "mode": "Rule-based (V2)"},
            "failed_rules": [{"rule_id": "CHK-ARITH-LINE-001", "rule_title": "Line total",
                              "finding": "mismatch", "evidence": "100 vs 90", "severity": "high"}],
            "preview_base64": "", "page_count": 1,
        }
    ],
    "findings": [],
}


def test_docx_report_is_docx_bytes():
    out = generate_docx_report(PAYLOAD)
    assert out[:4] == b"PK\x03\x04"
    assert len(out) > 500
    docx = Document(BytesIO(out))
    t = docx.tables[0]
    assert t.rows[1].cells[0].text == "CHK-ARITH-LINE-001" and t.rows[1].cells[1].text == "high"


def test_pdf_report_is_pdf_bytes():
    out = generate_pdf_report(PAYLOAD)
    assert out[:4] == b"%PDF"
    assert len(out) > 500
