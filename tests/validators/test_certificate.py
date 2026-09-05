from audit_v2.domain.catalog_loader import load_catalog
from audit_v2.domain.models import DocumentType, FindingStatus
from audit_v2.domain.validation import CheckRunner
from audit_v2.extraction.schemas import (
    CertificateOfOriginExtraction,
    to_extracted_document,
)


def _certificate():
    extracted = CertificateOfOriginExtraction.model_validate({
        "certificate_number": "COO-2026-217",
        "certificate_date": "18 August 2026",
        "exporter_name": "ABC Agro Exports Pvt. Ltd.",
        "consignee_name": "Green Valley Foods LLC",
        "goods": [{
            "description": "Premium Basmati Rice 5% Broken",
            "hs_code": "10063020",
            "quantity": "500",
            "quantity_unit": "MT",
            "invoice_number": "INV-2026-453",
            "invoice_date": "18.08.2026",
        }],
    })
    return to_extracted_document(
        extracted, document_id="doc_coo", tenant_id="tenant",
        doc_type=DocumentType.CERTIFICATE_OF_ORIGIN, page_count=1,
    )


def test_complete_certificate_passes_its_deterministic_checks() -> None:
    catalog = load_catalog()
    check_ids = [
        "CHK-CERT-MANDATORY-001", "CHK-CERT-GOODS-001", "CHK-CERT-REFERENCE-001",
    ]
    results = CheckRunner(catalog.checks).run_all(_certificate(), check_ids, {})
    assert [result.status for result in results] == [FindingStatus.PASS] * 3


def test_missing_certificate_reference_fails_only_reference_check() -> None:
    document = _certificate()
    document.header.referenced_invoice_number = None
    catalog = load_catalog()
    result = CheckRunner(catalog.checks).run_all(
        document, ["CHK-CERT-REFERENCE-001"], {},
    )[0]
    assert result.status == FindingStatus.FAIL
