"""Grounded presentation summaries over canonical audit facts."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from audit_v2.domain.models import ExtractedDocument, Finding
from audit_v2.gateway.nvidia_gateway import NvidiaGateway

DEFAULT_TEXT_MODEL = "meta/llama-3.3-70b-instruct"


def document_facts(
    doc: ExtractedDocument,
    findings: list[Finding],
    *,
    status: str,
    score: float | None,
    risk_level: str,
) -> dict[str, Any]:
    header = doc.header
    return {
        "document_id": doc.document_id,
        "document_type": doc.doc_type.value,
        "vendor": header.vendor_name.value if header.vendor_name else None,
        "buyer": header.buyer_name.value if header.buyer_name else None,
        "date": (
            header.invoice_date.value if header.invoice_date
            else header.order_date.value if header.order_date
            else header.delivery_date.value if header.delivery_date
            else header.grn_date.value if header.grn_date else None
        ),
        "reference": (
            header.invoice_number.value if header.invoice_number
            else header.po_number.value if header.po_number
            else header.challan_number.value if header.challan_number
            else header.grn_number.value if header.grn_number
            else header.po_reference.value if header.po_reference else None
        ),
        "grand_total": header.grand_total.value if header.grand_total else None,
        "line_item_count": len(doc.line_items),
        "status": status,
        "score": round(score, 2) if score is not None else None,
        "classification_status": doc.classification_status.value,
        "classification_confidence": round(doc.classification_confidence, 3),
        "certificate_number": (
            header.certificate_number.value if header.certificate_number else None
        ),
        "referenced_invoice": (
            header.referenced_invoice_number.value if header.referenced_invoice_number else None
        ),
        "certificate_goods_count": len(doc.certificate_goods),
        "risk_level": risk_level,
        "coverage_complete": doc.coverage.coverage_complete,
        "grounding_rejections": len(doc.grounding_rejections),
        "findings": [
            {
                "check_id": finding.check_id,
                "status": finding.status.value,
                "message": finding.message,
            }
            for finding in findings
        ],
    }


def deterministic_document_summary(facts: dict[str, Any]) -> str:
    parties = [value for value in (facts.get("vendor"), facts.get("buyer")) if value]
    subject = f" between {' and '.join(parties)}" if parties else ""
    first = f"This {str(facts['document_type']).replace('_', ' ')}{subject} was processed"
    if facts.get("date"):
        first += f" with document date {facts['date']}"
    first += "."
    details: list[str] = []
    if facts.get("grand_total"):
        details.append(f"stated total {facts['grand_total']}")
    if facts.get("document_type") == "certificate_of_origin":
        details.append(f"{facts.get('certificate_goods_count', 0)} grounded goods row(s)")
    else:
        details.append(f"{facts.get('line_item_count', 0)} grounded line item(s)")
    second = "The validated extraction contains " + " and ".join(details) + "."
    failures = len(facts.get("findings", []))
    if facts.get("score") is None:
        third = (
            f"Audit status is {facts['status']}; compliance is not scored until "
            "classification and extraction are confirmed. "
            f"{failures} deterministic finding(s) are recorded."
        )
    else:
        third = (
            f"Audit status is {facts['status']} with a score of {facts['score']:.1f}% "
            f"and {failures} finding(s); risk is {facts['risk_level']}."
        )
    if not facts.get("coverage_complete") or facts.get("grounding_rejections"):
        third += (
            " Human review is required because extraction evidence is incomplete or unsupported."
        )
    return " ".join((first, second, third))


def _numbers(text: str) -> set[str]:
    return {token.lstrip("0") or "0" for token in re.findall(r"\d+(?:\.\d+)?", text)}


def _polish_with_text_model(facts: dict[str, Any], fallback: str) -> str:
    if os.getenv("V2_SUMMARY_MODE", "deterministic").lower() != "always":
        return fallback
    if not os.getenv("NVIDIA_API_KEY"):
        return fallback
    gateway = NvidiaGateway(
        model=os.getenv("NVIDIA_TEXT_MODEL", DEFAULT_TEXT_MODEL), timeout=15, max_retries=0,
    )
    prompt = (
        "Write a concise 2-4 sentence audit overview using ONLY the JSON facts below. "
        "Do not add assumptions, calculations, legal conclusions, or facts not present. "
        "Return prose only.\n<facts>\n"
        f"{json.dumps(facts, default=str)}\n</facts>"
    )
    try:
        result = gateway.extract(images=[], prompt=prompt, tenant_id="summary")
        summary = result.content.strip()
        allowed = _numbers(json.dumps(facts, default=str))
        if summary and _numbers(summary).issubset(allowed):
            return summary
    except Exception:
        pass
    return fallback


def generate_document_summary(
    doc: ExtractedDocument,
    findings: list[Finding],
    *,
    status: str,
    score: float | None,
    risk_level: str,
) -> str:
    facts = document_facts(doc, findings, status=status, score=score, risk_level=risk_level)
    fallback = deterministic_document_summary(facts)
    return _polish_with_text_model(facts, fallback)


def deterministic_executive_summary(documents: list[dict[str, Any]]) -> str:
    total = len(documents)
    passed = sum(1 for doc in documents if doc.get("passed"))
    incomplete = sum(
        1 for doc in documents
        if doc.get("audit_status", "NOT_AUDITED" if doc.get("document_status") != "READY" else None)
        == "NOT_AUDITED"
    )
    review = sum(1 for doc in documents if doc.get("human_review_recommended"))
    high_risk = sum(1 for doc in documents if doc.get("risk_level") == "High Risk")
    failed = sum(
        1 for doc in documents
        if doc.get(
            "audit_status",
            "FAIL"
            if doc.get("document_status") == "READY" and not doc.get("passed")
            else None,
        )
        == "FAIL"
    )
    return (
        f"Audit processed {total} document(s): {passed} passed, {max(0, failed)} failed, "
        f"and {incomplete} remain incomplete or pending. {high_risk} document(s) are high risk "
        f"and {review} require human review."
    )


def generate_executive_summary(documents: list[dict[str, Any]]) -> str:
    fallback = deterministic_executive_summary(documents)
    facts = {
        "documents_processed": len(documents),
        "documents_passed": sum(1 for doc in documents if doc.get("passed")),
        "documents_incomplete": sum(
            1 for doc in documents
            if doc.get(
                "audit_status",
                "NOT_AUDITED" if doc.get("document_status") != "READY" else None,
            )
            == "NOT_AUDITED"
        ),
        "high_risk": sum(1 for doc in documents if doc.get("risk_level") == "High Risk"),
        "review_required": sum(1 for doc in documents if doc.get("human_review_recommended")),
    }
    return _polish_with_text_model(facts, fallback)
