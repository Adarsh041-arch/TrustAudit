"""Evidence-based document classification with a safe unknown fallback."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from audit_v2.domain.models import (
    ClassificationEvidence,
    ClassificationStatus,
    DocumentType,
)
from audit_v2.extraction.base import BaseExtractor
from audit_v2.extraction.document_profiles import DOCUMENT_PROFILES

logger = logging.getLogger(__name__)

EXTRACTOR_REGISTRY: dict[DocumentType, type[BaseExtractor]] = {}


@dataclass(frozen=True)
class ClassificationDecision:
    doc_type: DocumentType
    confidence: float
    status: ClassificationStatus
    method: str
    evidence: list[ClassificationEvidence] = field(default_factory=list)
    alternative_types: list[DocumentType] = field(default_factory=list)


def lazy_register() -> None:
    from audit_v2.extraction.delivery_challan_extractor import DeliveryChallanExtractor
    from audit_v2.extraction.grn_extractor import GRNExtractor
    from audit_v2.extraction.invoice_extractor import InvoiceExtractor
    from audit_v2.extraction.po_extractor import POExtractor

    EXTRACTOR_REGISTRY[DocumentType.INVOICE] = InvoiceExtractor
    EXTRACTOR_REGISTRY[DocumentType.PURCHASE_ORDER] = POExtractor
    EXTRACTOR_REGISTRY[DocumentType.DELIVERY_CHALLAN] = DeliveryChallanExtractor
    EXTRACTOR_REGISTRY[DocumentType.GOODS_RECEIPT_NOTE] = GRNExtractor


lazy_register()


def classify_document_detailed(
    text: str,
    *,
    method: str = "native_text",
    page: int = 1,
) -> ClassificationDecision:
    """Classify visible text; incidental field labels cannot beat document titles."""
    scores: dict[DocumentType, float] = {}
    title_scores: dict[DocumentType, float] = {}
    evidence_by_type: dict[DocumentType, list[ClassificationEvidence]] = {}

    for doc_type, profile in DOCUMENT_PROFILES.items():
        if doc_type == DocumentType.UNKNOWN:
            continue
        for signature in profile.signatures:
            match = signature.pattern.search(text)
            if match is None:
                continue
            scores[doc_type] = scores.get(doc_type, 0.0) + signature.weight
            if signature.title:
                title_scores[doc_type] = title_scores.get(doc_type, 0.0) + signature.weight
            evidence_text = (
                match.group("evidence")
                if "evidence" in signature.pattern.groupindex
                else match.group(0).strip(" |\t")
            )
            evidence_by_type.setdefault(doc_type, []).append(
                ClassificationEvidence(page=page, text=evidence_text)
            )

    if not scores:
        return ClassificationDecision(
            doc_type=DocumentType.UNKNOWN,
            confidence=0.0,
            status=ClassificationStatus.UNSUPPORTED,
            method=method,
        )

    ranking_source = title_scores or scores
    ranking = sorted(ranking_source, key=lambda item: ranking_source[item], reverse=True)
    winner = ranking[0]
    winner_score = ranking_source[winner]
    runner_up = ranking_source[ranking[1]] if len(ranking) > 1 else 0.0
    margin = winner_score - runner_up
    alternatives = [
        item
        for item in sorted(scores, key=lambda candidate: scores[candidate], reverse=True)
        if item != winner
    ]

    if title_scores:
        confirmed = margin >= 0.2 or len(ranking) == 1
        confidence = min(0.99, 0.8 + min(winner_score, 1.0) * 0.19)
    else:
        confirmed = winner_score >= 0.5 and margin >= 0.15
        confidence = min(0.89, 0.5 + min(winner_score, 1.0) * 0.4)

    if not confirmed:
        return ClassificationDecision(
            doc_type=DocumentType.UNKNOWN,
            confidence=min(confidence, 0.69),
            status=ClassificationStatus.AMBIGUOUS,
            method=method,
            evidence=evidence_by_type.get(winner, []),
            alternative_types=[winner, *alternatives],
        )

    return ClassificationDecision(
        doc_type=winner,
        confidence=confidence,
        status=ClassificationStatus.CONFIRMED,
        method=method,
        evidence=evidence_by_type.get(winner, []),
        alternative_types=alternatives,
    )


def classify_document(text: str) -> tuple[DocumentType, float]:
    decision = classify_document_detailed(text)
    return decision.doc_type, decision.confidence


def classify_document_from_data_detailed(data: bytes, mime_type: str) -> ClassificationDecision:
    text = data.decode("utf-8", errors="replace") if mime_type == "text/plain" else ""
    if not text and mime_type == "application/pdf":
        from audit_v2.extraction.text_extractor import TextExtractor

        try:
            pages = TextExtractor().extract_page_texts(data)
            text = "\n".join(pages.values())
        except Exception as err:
            logger.info("No usable PDF text layer: %s", err)

    return classify_document_detailed(text, method="native_text")


def classify_document_from_data(data: bytes, mime_type: str) -> tuple[DocumentType, float]:
    """Compatibility tuple API. Pixel classification happens in the GLM pipeline."""
    decision = classify_document_from_data_detailed(data, mime_type)
    return decision.doc_type, decision.confidence
