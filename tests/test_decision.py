"""Contract/letter auditability: key details validated -> PASS, unknown stays UNSUPPORTED."""
from audit_v2.domain.catalog_loader import load_catalog
from audit_v2.domain.decision import decide_document
from audit_v2.domain.models import (
    CheckResult,
    ClassificationStatus,
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
    FindingStatus,
    ProvenancedValue,
)

CATALOG = load_catalog().checks


def pv(value: str) -> ProvenancedValue:
    return ProvenancedValue(value=value, raw=value, page=1)


def make_doc(doc_type: DocumentType, **header_kwargs) -> ExtractedDocument:
    header = DocumentHeader(document_id="d", doc_type=doc_type, **header_kwargs)
    return ExtractedDocument(
        document_id="d", tenant_id="t", doc_type=doc_type, header=header,
        coverage=Coverage(pages_total=1, pages_examined=1, coverage_complete=True),
        page_count=1, extractor_version="test",
        classification_status=ClassificationStatus.CONFIRMED,
    )


def passed(check_id: str) -> CheckResult:
    return CheckResult(check_id=check_id, status=FindingStatus.PASS, message="ok")


def skipped(check_id: str) -> CheckResult:
    return CheckResult(check_id=check_id, status=FindingStatus.SKIPPED, message="n/a")


def test_contract_with_validated_key_details_passes():
    doc = make_doc(
        DocumentType.CONTRACT, vendor_name=pv("Seller"), buyer_name=pv("Buyer"),
        invoice_date=pv("2026-08-03"),
    )
    decision = decide_document(
        doc,
        [passed("CHK-FORMAT-MANDATORY-001"), skipped("CHK-TEMP-EXPIRY-001")],
        CATALOG,
    )
    assert decision.status == "PASS"
    assert decision.passed


def test_letter_with_validated_key_details_passes():
    doc = make_doc(
        DocumentType.LETTER, vendor_name=pv("Sender"), invoice_date=pv("2026-08-03")
    )
    decision = decide_document(doc, [passed("CHK-FORMAT-MANDATORY-001")], CATALOG)
    assert decision.status == "PASS"


def test_unknown_type_stays_unsupported():
    doc = make_doc(DocumentType.UNKNOWN)
    decision = decide_document(doc, [], CATALOG)
    assert decision.status == "UNSUPPORTED"
    assert not decision.passed


def test_contract_with_failed_mandatory_check_fails():
    doc = make_doc(
        DocumentType.CONTRACT, vendor_name=pv("Seller"), buyer_name=pv("Buyer"),
        invoice_date=pv("2026-08-03"),
    )
    failed = CheckResult(
        check_id="CHK-FORMAT-MANDATORY-001", status=FindingStatus.FAIL,
        expected="all mandatory fields", actual="missing: buyer_name",
        delta="N/A", message="Missing mandatory field(s): buyer_name",
    )
    decision = decide_document(doc, [failed], CATALOG)
    assert decision.status == "FAIL"


def test_disagreement_evidence_spells_out_conflict():
    from audit_v2.server import _disagreement_evidence

    doc = make_doc(DocumentType.INVOICE)
    assert _disagreement_evidence(doc) is None
    doc.extraction_disagreements = {"vendor_name": "Purchase Order vs ABC Agro"}
    evidence = _disagreement_evidence(doc)
    assert evidence is not None
    assert evidence.nature == "extracted_fields"
    assert "vendor_name" in evidence.summary
    assert "Purchase Order vs ABC Agro" in evidence.summary
    assert evidence.payload["disagreed_fields"] == ["vendor_name"]
