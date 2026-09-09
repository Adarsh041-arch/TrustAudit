"""The evidence-based document pipeline (new_requirements.md §3–§5).

``run_document_pipeline`` runs one document through the ladder the spec dictates
and returns a :class:`DocumentPipelineResult`: the canonical
:class:`ExtractedDocument` (for the deterministic validators to run over), the
ordered :class:`PipelineEvidence` trail, the LLM-detected
:class:`Contradiction`\\s, and whether the document needs a human.

Math-heavy docs (invoice / PO / DC / GRN) — sequential, each step an evidence:
    regex → OCR → VLM(structured) → VLM self-check/correct → arithmetic → metadata
Free-text docs (contract / letter):
    VLM(structured, with narrative) → metadata

Every collaborator that touches the network (VLM gateway, text gateway, OCR
engine) is injectable and degrades gracefully, so the pipeline runs — with fewer
evidences — when a key or package is missing, and is fully mockable in tests.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import BaseModel

from audit_v2.domain.evidence import (
    Contradiction,
    CrossCheckResult,
    EvidenceNature,
    PipelineEvidence,
)
from audit_v2.domain.models import (
    TEXT_DOC_TYPES,
    ClassificationStatus,
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
    ProvenancedValue,
)
from audit_v2.extraction.classifier import (
    EXTRACTOR_REGISTRY,
    ClassificationDecision,
    classify_document_detailed,
    classify_document_from_data_detailed,
)
from audit_v2.extraction.grounding import GroundingIssue, ground_instance
from audit_v2.extraction.merge import merge_extractions
from audit_v2.extraction.ocr_extractor import RapidOcrExtractor
from audit_v2.extraction.parser import parse_amount
from audit_v2.extraction.schemas import (
    EXTRACTION_SCHEMA_BY_TYPE,
    supplement_from_transcript,
    to_extracted_document,
)
from audit_v2.extraction.text_extractor import TextExtractor
from audit_v2.extraction.transcript_parser import SUPPORTED_TYPES, parse_transcript
from audit_v2.extraction.vlm_extractor import render_pages_to_jpeg
from audit_v2.gateway.nvidia_gateway import NvidiaGateway
from audit_v2.gateway.structured import extract_structured
from audit_v2.gateway.vision_factory import create_vision_gateway
from audit_v2.gateway.vision_gateway import VisionGateway
from audit_v2.pipeline.cross_check import run_cross_check
from audit_v2.pipeline.events import (
    NullProgressSink,
    PipelineStep,
    ProgressSink,
    StepStatus,
    emit,
)
from audit_v2.security.injection_detector import scan_document, scan_text

logger = logging.getLogger(__name__)

MATH_DOC_TYPES = frozenset(
    {
        DocumentType.INVOICE,
        DocumentType.PURCHASE_ORDER,
        DocumentType.DELIVERY_CHALLAN,
        DocumentType.GOODS_RECEIPT_NOTE,
    }
)


@dataclass
class DocumentPipelineResult:
    document_id: str
    doc_type: DocumentType
    document: ExtractedDocument | None
    evidences: list[PipelineEvidence] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    requires_human_review: bool = False
    cross_check: CrossCheckResult | None = None
    error: str | None = None


# ─── numeric / string comparison helpers ─────────────────────────────────────


def _dec(pv: ProvenancedValue | None) -> Decimal | None:
    if pv is None:
        return None
    try:
        return pv.decimal_value
    except ValueError:
        return None


def _to_decimal(raw: object) -> Decimal | None:
    if raw is None or str(raw).strip() == "":
        return None
    return parse_amount(str(raw))


def _amounts_disagree(a: Decimal, b: Decimal) -> bool:
    """True if two amounts differ beyond max(1% of the larger, 1.0)."""
    tol = max(abs(max(a, b, key=abs)) * Decimal("0.01"), Decimal("1"))
    return abs(a - b) > tol


def _norm_ref(s: object) -> str:
    return "".join(ch for ch in str(s).upper() if ch.isalnum())


# ─── evidence builders ───────────────────────────────────────────────────────


def _regex_evidence(document_id: str, doc: ExtractedDocument | None, note: str) -> PipelineEvidence:
    if doc is None:
        return PipelineEvidence(
            document_id=document_id,
            nature=EvidenceNature.OCR_REGEX_OBSERVATIONS,
            source="regex",
            payload={"available": False, "note": note},
            summary=f"Regex extraction unavailable: {note}",
            confidence=0.0,
        )
    gt = _dec(doc.header.grand_total)
    payload = {
        "available": True,
        "grand_total": str(gt) if gt is not None else None,
        "po_reference": doc.header.po_reference.value if doc.header.po_reference else None,
        "line_item_count": len(doc.line_items),
        "tax_line_count": len(doc.tax_lines),
    }
    return PipelineEvidence(
        document_id=document_id,
        nature=EvidenceNature.OCR_REGEX_OBSERVATIONS,
        source="regex",
        payload=payload,
        summary=(
            f"Regex read {len(doc.line_items)} line item(s); grand_total={payload['grand_total']}"
        ),
        confidence=0.9,
    )


def _ocr_evidence(document_id: str, fields: dict) -> PipelineEvidence:
    available = bool(fields.get("available"))
    if not available:
        return PipelineEvidence(
            document_id=document_id,
            nature=EvidenceNature.OCR_REGEX_OBSERVATIONS,
            source="rapidocr",
            payload=fields,
            summary=f"OCR unavailable: {fields.get('note', 'unknown')}",
            confidence=0.0,
        )
    return PipelineEvidence(
        document_id=document_id,
        nature=EvidenceNature.OCR_REGEX_OBSERVATIONS,
        source="rapidocr",
        payload=fields,
        summary=(
            f"OCR read grand_total≈{fields.get('grand_total')}, "
            f"po_reference={fields.get('po_reference')} "
            f"(mean conf {fields.get('mean_confidence')})"
        ),
        confidence=float(fields.get("mean_confidence") or 0.5),
    )


def _vlm_evidence(
    document_id: str, instance: BaseModel, source: str, page: int
) -> PipelineEvidence:
    return PipelineEvidence(
        document_id=document_id,
        nature=EvidenceNature.VLM_OBSERVATIONS,
        source=source,
        payload=instance.model_dump(mode="json"),
        summary=f"Local vision ({source}) structured extraction for page {page}",
        confidence=0.85,
        page=page,
    )


def _compute_arithmetic(doc: ExtractedDocument) -> dict:
    """Compute the spec's arithmetic evidence (§4) with Decimal, guarding NaNs."""
    total_quantity = Decimal("0")
    stated_line_sum = Decimal("0")
    computed_line_sum = Decimal("0")
    for li in doc.line_items:
        qty = _dec(li.quantity)
        if qty is not None:
            total_quantity += qty
        stated = _dec(li.line_total)
        if stated is not None:
            stated_line_sum += stated
        computed_line_sum += li.expected_total()

    tax_total = Decimal("0")
    for tl in doc.tax_lines:
        t = _dec(tl.total_tax)
        if t is not None:
            tax_total += t

    subtotal = _dec(doc.header.subtotal)
    discount = _dec(doc.header.discount_amount) or Decimal("0")
    grand_total = _dec(doc.header.grand_total)
    expected_grand = None
    if subtotal is not None:
        expected_grand = subtotal + tax_total - discount

    return {
        "total_quantity": str(total_quantity),
        "computed_line_items_total": str(computed_line_sum),
        "stated_line_items_total": str(stated_line_sum),
        "tax_total": str(tax_total),
        "subtotal": str(subtotal) if subtotal is not None else None,
        "discount": str(discount),
        "expected_grand_total": str(expected_grand) if expected_grand is not None else None,
        "stated_grand_total": str(grand_total) if grand_total is not None else None,
    }


def _arithmetic_evidence(document_id: str, doc: ExtractedDocument) -> PipelineEvidence:
    payload = _compute_arithmetic(doc)
    return PipelineEvidence(
        document_id=document_id,
        nature=EvidenceNature.ARITHMETIC_COMPUTATION,
        source="arithmetic",
        payload=payload,
        summary=(
            f"Computed line total={payload['computed_line_items_total']}, "
            f"tax={payload['tax_total']}, expected grand_total="
            f"{payload['expected_grand_total']} vs stated {payload['stated_grand_total']}"
        ),
        confidence=1.0,
    )


def _metadata_evidence(
    document_id: str,
    *,
    filename: str | None,
    mime_type: str,
    page_count: int,
    doc_type: DocumentType,
    classification_confidence: float,
    classification_status: ClassificationStatus,
    classification_method: str,
    classification_evidence: list[object],
    alternative_types: list[DocumentType],
    extractor_version: str,
) -> PipelineEvidence:
    payload = {
        "filename": filename,
        "mime_type": mime_type,
        "page_count": page_count,
        "doc_type": doc_type.value,
        "classification_confidence": classification_confidence,
        "classification_status": classification_status.value,
        "classification_method": classification_method,
        "classification_evidence": [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else str(item)
            for item in classification_evidence
        ],
        "alternative_types": [item.value for item in alternative_types],
        "extractor_version": extractor_version,
    }
    return PipelineEvidence(
        document_id=document_id,
        nature=EvidenceNature.METADATA,
        source="metadata",
        payload=payload,
        summary=f"{doc_type.value} · {page_count} page(s) · {mime_type}",
        confidence=1.0,
    )


# ─── extraction steps ────────────────────────────────────────────────────────


def _run_regex(
    data: bytes, mime_type: str, document_id: str, tenant_id: str, doc_type: DocumentType
) -> tuple[ExtractedDocument | None, str]:
    extractor_cls = EXTRACTOR_REGISTRY.get(doc_type)
    if extractor_cls is None:
        return None, f"no regex extractor for {doc_type.value}"
    try:
        doc = extractor_cls().extract(data, mime_type)
        doc.document_id = document_id
        doc.tenant_id = tenant_id
        return doc, "ok"
    except Exception as err:
        logger.warning("Regex extraction failed for %s: %s", document_id, err)
        return None, str(err)


def _vlm_prompt(doc_type: DocumentType) -> str:
    return (
        f"You are a high-precision {doc_type.value} extraction engine. Read the "
        "single document page and extract only values visibly printed on it. "
        "Never calculate, repair, reconcile, or infer a missing value. Use "
        "null for any field not present. Put anything salient the fixed fields "
        "do not capture into 'other_necessary_details' as short strings. Write "
        'monetary amounts as plain numeric strings (e.g. "1250.00"). Return '
        "ONLY the JSON object."
    )


def _recovery_prompt(doc_type: DocumentType, reasons: list[str]) -> str:
    requested = ", ".join(reason.split(":", 1)[-1] for reason in reasons)
    return (
        f"Recover only these unresolved {doc_type.value} fields from this page: "
        f"{requested}. Use null for anything not visibly printed. Never calculate "
        "or infer values. Return only the schema JSON object."
    )


def _transcribe_page(gateway: VisionGateway, image: bytes, tenant_id: str) -> tuple[str, str, bool]:
    transcribe = getattr(gateway, "transcribe", None)
    if callable(transcribe):
        response = transcribe(image, tenant_id)
        if scan_text(response.content):
            raise ValueError("Suspicious instructions in document transcription")
        return (
            response.content.strip(),
            response.model_version,
            bool(getattr(gateway, "last_cache_hit", False)),
        )
    response = gateway.extract(
        images=[image],
        prompt="Text Recognition:",
        tenant_id=tenant_id,
    )
    if scan_text(response.content):
        raise ValueError("Suspicious instructions in document transcription")
    return response.content.strip(), response.model_version, False


def _self_check(
    vlm_instance: BaseModel,
    regex_doc: ExtractedDocument | None,
    ocr_fields: dict,
) -> dict[str, str]:
    """Compare VLM fields against corroborating regex+OCR reads on shared keys."""
    disagreements: dict[str, str] = {}

    vlm_gt = _to_decimal(getattr(vlm_instance, "grand_total", None))
    corro_gt = _dec(regex_doc.header.grand_total) if regex_doc else None
    if corro_gt is None and ocr_fields.get("available") and ocr_fields.get("grand_total"):
        corro_gt = parse_amount(str(ocr_fields["grand_total"]))
    if vlm_gt is not None and corro_gt is not None and _amounts_disagree(vlm_gt, corro_gt):
        disagreements["grand_total"] = f"vlm={vlm_gt} vs corroborated={corro_gt}"

    vlm_po = getattr(vlm_instance, "po_reference", None) or getattr(vlm_instance, "po_number", None)
    corro_po = (
        regex_doc.header.po_reference.value if regex_doc and regex_doc.header.po_reference else None
    )
    if corro_po is None and ocr_fields.get("available"):
        corro_po = ocr_fields.get("po_reference")
    if vlm_po and corro_po and _norm_ref(vlm_po) != _norm_ref(corro_po):
        disagreements["po_reference"] = f"vlm={vlm_po} vs corroborated={corro_po}"

    return disagreements


def _empty_document(
    document_id: str, tenant_id: str, doc_type: DocumentType, page_count: int
) -> ExtractedDocument:
    pages = max(1, page_count)
    return ExtractedDocument(
        document_id=document_id,
        tenant_id=tenant_id,
        doc_type=doc_type,
        header=DocumentHeader(document_id=document_id, doc_type=doc_type),
        coverage=Coverage(pages_total=pages, pages_examined=0, coverage_complete=False),
        page_count=pages,
        extractor_version="pipeline_empty_1.0.0",
    )


def _set_page_provenance(doc: ExtractedDocument, page: int) -> None:
    """Assign the source page to every value created from one page request."""
    for field_name in doc.header.__class__.model_fields:
        value = getattr(doc.header, field_name)
        if isinstance(value, ProvenancedValue):
            value.page = page
    for line in doc.line_items:
        for field_name in line.__class__.model_fields:
            value = getattr(line, field_name)
            if isinstance(value, ProvenancedValue):
                value.page = page
    for tax in doc.tax_lines:
        for field_name in tax.__class__.model_fields:
            value = getattr(tax, field_name)
            if isinstance(value, ProvenancedValue):
                value.page = page
    for goods in doc.certificate_goods:
        for field_name in goods.__class__.model_fields:
            value = getattr(goods, field_name)
            if isinstance(value, ProvenancedValue):
                value.page = page


def _merge_glm_pages(
    documents: list[ExtractedDocument],
    *,
    document_id: str,
    tenant_id: str,
    doc_type: DocumentType,
    page_count: int,
    unreadable: list[int],
    issues: list[GroundingIssue],
    model_version: str,
    vision_backend: str,
) -> ExtractedDocument:
    """Combine independently grounded page reads without hiding conflicts."""
    if not documents:
        empty = _empty_document(document_id, tenant_id, doc_type, page_count)
        empty.extractor_version = f"{vision_backend}_empty_1.0.0"
        empty.model_version = model_version
        empty.vision_backend = vision_backend
        empty.grounding_rejections = [issue.message() for issue in issues]
        return empty

    merged = documents[0].model_copy(deep=True)
    disagreements: dict[str, str] = {}
    for page_doc in documents[1:]:
        for field_name in page_doc.header.__class__.model_fields:
            if field_name in {"document_id", "doc_type", "bank_details"}:
                continue
            current = getattr(merged.header, field_name)
            incoming = getattr(page_doc.header, field_name)
            if current is None and incoming is not None:
                setattr(merged.header, field_name, incoming)
            elif (
                isinstance(current, ProvenancedValue)
                and isinstance(incoming, ProvenancedValue)
                and _norm_ref(current.value) != _norm_ref(incoming.value)
            ):
                disagreements[f"page_{incoming.page}.{field_name}"] = (
                    f"page {current.page}={current.raw} vs page {incoming.page}={incoming.raw}"
                )
        if merged.header.bank_details is None and page_doc.header.bank_details:
            merged.header.bank_details = page_doc.header.bank_details
        merged.line_items.extend(page_doc.line_items)
        merged.tax_lines.extend(page_doc.tax_lines)
        merged.certificate_goods.extend(page_doc.certificate_goods)
        if page_doc.narrative_report and page_doc.narrative_report != merged.narrative_report:
            merged.narrative_report = " ".join(
                item for item in (merged.narrative_report, page_doc.narrative_report) if item
            )

    for index, line in enumerate(merged.line_items, start=1):
        line.line_number = index
    for index, tax in enumerate(merged.tax_lines, start=1):
        tax.line_number = index
    for index, goods in enumerate(merged.certificate_goods, start=1):
        goods.line_number = index
    examined = page_count - len(set(unreadable))
    merged.document_id = document_id
    merged.tenant_id = tenant_id
    merged.doc_type = doc_type
    merged.header.document_id = document_id
    merged.header.doc_type = doc_type
    merged.page_count = page_count
    merged.coverage = Coverage(
        pages_total=page_count,
        pages_examined=examined,
        pages_unreadable=sorted(set(unreadable)),
        coverage_complete=examined == page_count and not unreadable,
    )
    merged.extractor_version = f"{vision_backend}_grounded_1.0.0"
    merged.model_version = model_version
    merged.vision_backend = vision_backend
    merged.grounding_rejections = [issue.message() for issue in issues]
    merged.extraction_disagreements.update(disagreements)
    return merged


def _run_glm_pages(
    *,
    images: list[bytes],
    document_id: str,
    tenant_id: str,
    doc_type: DocumentType,
    gateway: VisionGateway,
    evidences: list[PipelineEvidence],
    transcripts: dict[int, str] | None = None,
) -> tuple[ExtractedDocument, list[GroundingIssue]]:
    """Run transcript-first grounded extraction independently for every page."""
    schema_model = EXTRACTION_SCHEMA_BY_TYPE[doc_type]
    page_documents: list[ExtractedDocument] = []
    unreadable: list[int] = []
    issues: list[GroundingIssue] = []
    model_version = getattr(gateway, "model", "unknown")
    vision_backend = getattr(gateway, "backend", "glm_ocr")
    transcripts = transcripts or {}
    network_calls_before = int(getattr(gateway, "network_call_count", 0))
    cache_hit = False
    fallback_used = False
    fallback_reasons: list[str] = []

    for page, image in enumerate(images, start=1):
        try:
            transcript = transcripts.get(page, "").strip()
            if not transcript:
                transcript, model_version, hit = _transcribe_page(gateway, image, tenant_id)
                cache_hit = cache_hit or hit
            if not transcript:
                raise ValueError("empty transcription")
            evidences.append(
                PipelineEvidence(
                    document_id=document_id,
                    nature=EvidenceNature.OCR_REGEX_OBSERVATIONS,
                    source=f"{vision_backend}_transcription",
                    payload={
                        "text": transcript[:12000],
                        "truncated": len(transcript) > 12000,
                    },
                    summary=f"{vision_backend} transcribed page {page}",
                    confidence=0.85,
                    page=page,
                )
            )

            page_issues: list[GroundingIssue] = []
            page_disagreements: dict[str, str] = {}
            if (
                doc_type in SUPPORTED_TYPES
                and os.getenv("V2_EXTRACTION_POLICY", "balanced") == "balanced"
            ):
                parsed = parse_transcript(doc_type, transcript, first_page=page == 1)
                deterministic = ground_instance(parsed.instance, transcript, page)
                page_issues.extend(deterministic.issues)
                evidences.append(
                    _vlm_evidence(
                        document_id,
                        deterministic.instance,
                        f"{vision_backend}_transcript_deterministic",
                        page,
                    )
                )
                page_doc = to_extracted_document(
                    deterministic.instance,
                    document_id=document_id,
                    tenant_id=tenant_id,
                    doc_type=doc_type,
                    page_count=1,
                    extractor_version=f"{vision_backend}_transcript_1.0.0",
                )
                if parsed.fallback_reasons:
                    fallback_used = True
                    fallback_reasons.extend(
                        f"page {page} {reason}" for reason in parsed.fallback_reasons
                    )
                    try:
                        recovered = extract_structured(
                            gateway=gateway,
                            images=[image],
                            prompt=_recovery_prompt(doc_type, parsed.fallback_reasons),
                            schema_model=schema_model,
                            tenant_id=tenant_id,
                            max_tokens=int(
                                getattr(
                                    gateway,
                                    "structured_max_tokens",
                                    os.getenv("GLM_OCR_STRUCTURED_MAX_TOKENS", "1536"),
                                )
                            ),
                        )
                        recovered = supplement_from_transcript(recovered, doc_type, transcript)
                        grounded_recovery = ground_instance(recovered, transcript, page)
                        page_issues.extend(grounded_recovery.issues)
                        evidences.append(
                            _vlm_evidence(
                                document_id,
                                grounded_recovery.instance,
                                f"{vision_backend}_structured",
                                page,
                            )
                        )
                        recovered_doc = to_extracted_document(
                            grounded_recovery.instance,
                            document_id=document_id,
                            tenant_id=tenant_id,
                            doc_type=doc_type,
                            page_count=1,
                            extractor_version=f"{vision_backend}_recovery_1.0.0",
                        )
                        merge = merge_extractions(page_doc, recovered_doc)
                        page_doc = merge.merged
                        page_disagreements.update(merge.disagreements)
                    except Exception as recovery_error:
                        logger.warning(
                            "Structured recovery failed on page %d: %s",
                            page,
                            recovery_error,
                        )
                        page_issues.append(
                            GroundingIssue(
                                "structured_fallback",
                                str(recovery_error),
                                page,
                                "targeted structured fallback failed",
                            )
                        )
            else:
                instance = extract_structured(
                    gateway=gateway,
                    images=[image],
                    prompt=_vlm_prompt(doc_type),
                    schema_model=schema_model,
                    tenant_id=tenant_id,
                )
                instance = supplement_from_transcript(instance, doc_type, transcript)
                grounded = ground_instance(instance, transcript, page)
                page_issues.extend(grounded.issues)
                evidences.append(
                    _vlm_evidence(
                        document_id,
                        grounded.instance,
                        f"{vision_backend}_structured",
                        page,
                    )
                )
                page_doc = to_extracted_document(
                    grounded.instance,
                    document_id=document_id,
                    tenant_id=tenant_id,
                    doc_type=doc_type,
                    page_count=1,
                    extractor_version=f"{vision_backend}_page_1.0.0",
                )

            issues.extend(page_issues)
            for issue in page_issues:
                evidences.append(
                    PipelineEvidence(
                        document_id=document_id,
                        nature=EvidenceNature.EXTRACTED_FIELDS,
                        source="grounding_rejection",
                        payload={
                            "field": issue.field,
                            "candidate": issue.candidate,
                            "reason": issue.reason,
                        },
                        summary=f"Rejected unsupported value for {issue.field}",
                        confidence=1.0,
                        page=page,
                    )
                )
            page_doc.model_version = model_version
            page_doc.extraction_disagreements.update(page_disagreements)
            _set_page_provenance(page_doc, page)
            page_documents.append(page_doc)
        except Exception as exc:
            logger.warning("Vision page %d failed for %s: %s", page, document_id, exc)
            unreadable.append(page)
            evidences.append(
                PipelineEvidence(
                    document_id=document_id,
                    nature=EvidenceNature.OCR_REGEX_OBSERVATIONS,
                    source=f"{vision_backend}_transcription",
                    payload={"available": False, "error": str(exc)},
                    summary=f"{vision_backend} could not read page {page}",
                    confidence=0.0,
                    page=page,
                )
            )

    merged = _merge_glm_pages(
        page_documents,
        document_id=document_id,
        tenant_id=tenant_id,
        doc_type=doc_type,
        page_count=max(1, len(images)),
        unreadable=unreadable,
        issues=issues,
        model_version=model_version,
        vision_backend=vision_backend,
    )
    observed_calls = int(getattr(gateway, "network_call_count", 0)) - network_calls_before
    if observed_calls == 0 and hasattr(gateway, "calls"):
        observed_calls = len(gateway.calls)
    merged.vision_call_count = max(0, observed_calls)
    merged.glm_call_count = merged.vision_call_count if vision_backend == "glm_ocr" else 0
    merged.structured_fallback_used = fallback_used
    merged.transcript_cache_hit = cache_hit
    merged.fallback_reasons = fallback_reasons
    merged.extraction_strategy = (
        "transcript_plus_structured_fallback"
        if fallback_used
        else "transcript_only"
        if doc_type in SUPPORTED_TYPES
        else "transcript_plus_structured_fallback"
    )
    return merged, issues


# ─── the pipeline ─────────────────────────────────────────────────────────────


def run_document_pipeline(
    data: bytes,
    mime_type: str,
    document_id: str,
    tenant_id: str,
    *,
    filename: str | None = None,
    doc_type: DocumentType | None = None,
    sink: ProgressSink | None = None,
    vlm_gateway: VisionGateway | None = None,
    text_gateway: NvidiaGateway | None = None,
    ocr: RapidOcrExtractor | None = None,
) -> DocumentPipelineResult:
    started = time.monotonic()
    sink = sink or NullProgressSink()
    ocr = ocr or RapidOcrExtractor()
    evidences: list[PipelineEvidence] = []

    if mime_type == "application/pdf":
        try:
            native_text = "\n".join(b["text"] for b in TextExtractor().extract_text_blocks(data))
        except RuntimeError:
            native_text = ""
        scan = scan_document(native_text, data)
        if scan.is_suspicious:
            return DocumentPipelineResult(
                document_id=document_id,
                doc_type=doc_type or DocumentType.UNKNOWN,
                document=None,
                requires_human_review=True,
                error=f"QUARANTINED_SECURITY: {scan.summary()}",
            )

    # Page images are rendered before classification so scanned documents can
    # be classified from local transcription, never NVIDIA vision.
    try:
        images = render_pages_to_jpeg(data, mime_type)
    except Exception as err:
        logger.info("Could not render pages for %s: %s", document_id, err)
        images = []
    page_count = max(1, len(images))

    # The configured local gateway is the vision lane. NVIDIA remains text-only.
    if vlm_gateway is None:
        vlm_gateway = create_vision_gateway()
    vlm_available = vlm_gateway is not None and bool(images)
    gateway_calls_before = (
        int(getattr(vlm_gateway, "network_call_count", 0)) if vlm_gateway is not None else 0
    )
    fake_calls_before = len(getattr(vlm_gateway, "calls", [])) if vlm_gateway is not None else 0
    classification_cache_hit = False
    page_transcripts: dict[int, str] = {}

    # ── 1. classify ──────────────────────────────────────────────────────────
    emit(sink, document_id, PipelineStep.CLASSIFY, StepStatus.START)
    if doc_type is not None:
        classification = ClassificationDecision(
            doc_type=doc_type,
            confidence=1.0,
            status=ClassificationStatus.CONFIRMED,
            method="provided",
        )
    else:
        try:
            classification = classify_document_from_data_detailed(data, mime_type)
        except Exception as err:
            logger.warning("Native classification failed for %s: %s", document_id, err)
            classification = ClassificationDecision(
                doc_type=DocumentType.UNKNOWN,
                confidence=0.0,
                status=ClassificationStatus.UNSUPPORTED,
                method="native_text",
            )

        if (
            classification.doc_type == DocumentType.UNKNOWN
            and vlm_available
            and vlm_gateway is not None
        ):
            try:
                transcript, _model, classification_cache_hit = _transcribe_page(
                    vlm_gateway, images[0], tenant_id
                )
                page_transcripts[1] = transcript
                backend = getattr(vlm_gateway, "backend", "local_vision")
                classification = classify_document_detailed(
                    page_transcripts[1],
                    method=f"{backend}_transcription",
                    page=1,
                )
            except Exception as err:
                logger.warning(
                    "Vision classification transcription failed for %s: %s",
                    document_id,
                    err,
                )

    doc_type = classification.doc_type
    classification_confidence = classification.confidence
    emit(
        sink,
        document_id,
        PipelineStep.CLASSIFY,
        (
            StepStatus.OK
            if classification.status == ClassificationStatus.CONFIRMED
            else StepStatus.SKIP
        ),
        detail=f"{doc_type.value} ({classification.status.value})",
        doc_type=doc_type.value,
    )

    requires_human_review = False
    document: ExtractedDocument | None = None

    if doc_type in TEXT_DOC_TYPES:
        document = _run_text_pipeline(
            data,
            mime_type,
            document_id,
            tenant_id,
            doc_type,
            images,
            page_count,
            vlm_gateway if vlm_available else None,
            sink,
            evidences,
            page_transcripts,
        )
    else:
        document, requires_human_review = _run_math_pipeline(
            data,
            mime_type,
            document_id,
            tenant_id,
            doc_type,
            images,
            page_count,
            vlm_gateway if vlm_available else None,
            ocr,
            sink,
            evidences,
            page_transcripts,
        )

    if document is not None:
        document.classification_status = classification.status
        document.classification_confidence = classification.confidence
        document.classification_method = classification.method
        document.classification_evidence = classification.evidence
        document.alternative_types = classification.alternative_types
        document.extraction_latency_ms = round((time.monotonic() - started) * 1000, 2)
        if vlm_gateway is not None:
            real_calls = (
                int(getattr(vlm_gateway, "network_call_count", gateway_calls_before))
                - gateway_calls_before
            )
            fake_calls = len(getattr(vlm_gateway, "calls", [])) - fake_calls_before
            document.vision_call_count = max(0, real_calls or fake_calls)
            backend = getattr(vlm_gateway, "backend", "glm_ocr")
            document.vision_backend = backend
            document.glm_call_count = document.vision_call_count if backend == "glm_ocr" else 0
            document.transcript_cache_hit = (
                document.transcript_cache_hit or classification_cache_hit
            )

    if document is not None and (
        document.grounding_rejections or not document.coverage.coverage_complete
    ):
        requires_human_review = True

    # ── metadata evidence (every doc) ─────────────────────────────────────────
    extractor_version = document.extractor_version if document else "none"
    evidences.append(
        _metadata_evidence(
            document_id,
            filename=filename,
            mime_type=mime_type,
            page_count=page_count,
            doc_type=doc_type,
            classification_confidence=classification_confidence,
            classification_status=classification.status,
            classification_method=classification.method,
            classification_evidence=list(classification.evidence),
            alternative_types=list(classification.alternative_types),
            extractor_version=extractor_version,
        )
    )

    # Preserve lineage: parsing and arithmetic are derived observations.
    for evidence in evidences:
        if evidence.source in {"glm_ocr_transcript_deterministic", "glm_ocr_structured"}:
            evidence.derived_from = [
                e.evidence_id
                for e in evidences
                if e.source == "glm_ocr_transcription"
                and (e.page == evidence.page or evidence.page is None)
            ]
        elif evidence.source == "arithmetic":
            evidence.derived_from = [
                e.evidence_id
                for e in evidences
                if e.source
                in {"regex", "rapidocr", "glm_ocr_transcript_deterministic", "glm_ocr_structured"}
            ]

    # ── cross-check (§5) ───────────────────────────────────────────────────────
    emit(sink, document_id, PipelineStep.CROSS_CHECK, StepStatus.START)
    cross_mode = os.getenv("V2_CROSS_CHECK_MODE", "on_review").lower()
    uncertain = (
        classification.status != ClassificationStatus.CONFIRMED
        or requires_human_review
        or document is None
        or bool(document.grounding_rejections)
        or bool(document.extraction_disagreements)
        or not document.coverage.coverage_complete
    )
    if cross_mode == "always" or (cross_mode == "on_review" and uncertain):
        cross = run_cross_check(
            evidences,
            document_id,
            doc_type,
            tenant_id,
            gateway=text_gateway,
        )
    else:
        cross = CrossCheckResult(
            document_id=document_id,
            supported=None,
            execution_status="not_requested",
            summary=f"cross-check skipped by {cross_mode} policy",
        )
    if document is not None and any(
        item.nature == EvidenceNature.METADATA and item.confidence >= 0.8
        for item in cross.contradictions
    ):
        document.classification_status = ClassificationStatus.CONFLICTED
        requires_human_review = True
    emit(
        sink,
        document_id,
        PipelineStep.CROSS_CHECK,
        StepStatus.OK,
        detail=f"{len(cross.contradictions)} contradiction(s)",
        contradictions=len(cross.contradictions),
    )

    error = None if document is not None else "extraction produced no document"
    return DocumentPipelineResult(
        document_id=document_id,
        doc_type=doc_type,
        document=document,
        evidences=evidences,
        contradictions=cross.contradictions,
        requires_human_review=requires_human_review,
        cross_check=cross,
        error=error,
    )


def _run_math_pipeline(
    data: bytes,
    mime_type: str,
    document_id: str,
    tenant_id: str,
    doc_type: DocumentType,
    images: list[bytes],
    page_count: int,
    vlm_gateway: VisionGateway | None,
    ocr: RapidOcrExtractor,
    sink: ProgressSink,
    evidences: list[PipelineEvidence],
    page_transcripts: dict[int, str],
) -> tuple[ExtractedDocument | None, bool]:
    """regex → OCR → VLM(structured) → self-check → arithmetic (spec §3–§4)."""
    emit(sink, document_id, PipelineStep.EXTRACT_OCR, StepStatus.START)
    ocr_pool = ThreadPoolExecutor(max_workers=1)
    ocr_future = ocr_pool.submit(ocr.extract_fields, images, doc_type) if images else None

    # 1. regex
    emit(sink, document_id, PipelineStep.EXTRACT_REGEX, StepStatus.START)
    regex_doc, regex_note = _run_regex(data, mime_type, document_id, tenant_id, doc_type)
    evidences.append(_regex_evidence(document_id, regex_doc, regex_note))
    emit(
        sink,
        document_id,
        PipelineStep.EXTRACT_REGEX,
        StepStatus.OK if regex_doc else StepStatus.SKIP,
        detail=regex_note,
    )

    # 2. Local GLM-OCR runs while CPU RapidOCR is working independently.
    vlm_doc: ExtractedDocument | None = None
    requires_human_review = False
    if vlm_gateway is not None:
        emit(sink, document_id, PipelineStep.EXTRACT_VLM, StepStatus.START)
        try:
            vlm_doc, grounding_issues = _run_glm_pages(
                images=images,
                document_id=document_id,
                tenant_id=tenant_id,
                doc_type=doc_type,
                gateway=vlm_gateway,
                evidences=evidences,
                transcripts=page_transcripts,
            )
            emit(sink, document_id, PipelineStep.EXTRACT_VLM, StepStatus.OK)
            emit(sink, document_id, PipelineStep.VLM_SELFCHECK, StepStatus.START)
            requires_human_review = bool(grounding_issues) or not vlm_doc.coverage.coverage_complete
            emit(
                sink,
                document_id,
                PipelineStep.VLM_SELFCHECK,
                StepStatus.OK,
                detail=f"{len(grounding_issues)} grounding rejection(s)",
            )
        except Exception as err:
            logger.warning("GLM-OCR grounded extraction failed for %s: %s", document_id, err)
            emit(sink, document_id, PipelineStep.EXTRACT_VLM, StepStatus.ERROR, detail=str(err))
    else:
        emit(sink, document_id, PipelineStep.EXTRACT_VLM, StepStatus.SKIP, detail="no VLM gateway")

    try:
        ocr_fields = (
            ocr_future.result()
            if ocr_future is not None
            else {
                "available": False,
                "note": "no page images to OCR",
            }
        )
    except Exception as ocr_error:
        ocr_fields = {"available": False, "note": str(ocr_error)}
    finally:
        ocr_pool.shutdown(wait=True)
    evidences.append(_ocr_evidence(document_id, ocr_fields))
    emit(
        sink,
        document_id,
        PipelineStep.EXTRACT_OCR,
        StepStatus.OK if ocr_fields.get("available") else StepStatus.SKIP,
        detail=str(ocr_fields.get("note", "ok")),
    )

    # canonical document: regex authoritative when both present (merge records
    # field-level disagreements too); otherwise whichever we have.
    document = _pick_document(regex_doc, vlm_doc, document_id, tenant_id, doc_type, page_count)
    if document is None:
        document = _empty_document(document_id, tenant_id, doc_type, page_count)
        requires_human_review = True
    elif vlm_doc is None and regex_doc is not None:
        document.extraction_strategy = "native_regex"
    if document is not None and document.extraction_disagreements:
        requires_human_review = True

    # 5. arithmetic evidence
    if document is not None:
        emit(sink, document_id, PipelineStep.ARITHMETIC, StepStatus.START)
        evidences.append(_arithmetic_evidence(document_id, document))
        emit(sink, document_id, PipelineStep.ARITHMETIC, StepStatus.OK)

    return document, requires_human_review


def _pick_document(
    regex_doc: ExtractedDocument | None,
    vlm_doc: ExtractedDocument | None,
    document_id: str,
    tenant_id: str,
    doc_type: DocumentType,
    page_count: int,
) -> ExtractedDocument | None:
    if regex_doc is not None and vlm_doc is not None:
        merged = merge_extractions(regex_doc, vlm_doc).merged
        merged.document_id = document_id
        merged.tenant_id = tenant_id
        return merged
    return regex_doc or vlm_doc


def _run_text_pipeline(
    data: bytes,
    mime_type: str,
    document_id: str,
    tenant_id: str,
    doc_type: DocumentType,
    images: list[bytes],
    page_count: int,
    vlm_gateway: VisionGateway | None,
    sink: ProgressSink,
    evidences: list[PipelineEvidence],
    page_transcripts: dict[int, str],
) -> ExtractedDocument | None:
    """Free-text docs: grounded local extraction; narrative is advisory."""
    if vlm_gateway is None:
        emit(sink, document_id, PipelineStep.EXTRACT_VLM, StepStatus.SKIP, detail="no VLM gateway")
        return _empty_document(document_id, tenant_id, doc_type, page_count)

    emit(sink, document_id, PipelineStep.EXTRACT_VLM, StepStatus.START)
    try:
        document, _issues = _run_glm_pages(
            images=images,
            document_id=document_id,
            tenant_id=tenant_id,
            doc_type=doc_type,
            gateway=vlm_gateway,
            evidences=evidences,
            transcripts=page_transcripts,
        )
        emit(sink, document_id, PipelineStep.EXTRACT_VLM, StepStatus.OK)
        return document
    except Exception as err:
        logger.warning("VLM text extraction failed for %s: %s", document_id, err)
        emit(sink, document_id, PipelineStep.EXTRACT_VLM, StepStatus.ERROR, detail=str(err))
        return _empty_document(document_id, tenant_id, doc_type, page_count)


def _correction_prompt(doc_type: DocumentType, disagreements: dict[str, str]) -> str:
    lines = "\n".join(f"- {k}: {v}" for k, v in disagreements.items())
    return (
        f"{_vlm_prompt(doc_type)}\n\n"
        "A prior read of this document disagreed with independent OCR/regex "
        f"reads on these fields:\n{lines}\n"
        "Re-examine the document image carefully and return corrected JSON."
    )
