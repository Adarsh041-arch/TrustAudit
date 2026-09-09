"""Cross-document correlation — Phase 7 (PHASES_V2 §4).

Builds TransactionClusters from extracted documents. Pure domain code: no
network, no model calls, deterministic for a given input set.

Linkage priority (highest first):
1. explicit reference — invoice/DC/GRN cites a PO number  (confidence 0.98)
2. (vendor, amount, date-window)                          (confidence 0.80)
3. fuzzy — vendor + line-description overlap              (confidence 0.60)

Every link records its method and confidence. Low-confidence links are
included but flagged; the adjudicator/review layer decides whether to assert.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from audit_v2.domain.models import (
    CorpusIndex,
    DocumentLink,
    DocumentType,
    ExtractedDocument,
    LinkMethod,
    TransactionCluster,
)

# ponytail: fixed thresholds; make tenant-configurable when a tenant asks.
DATE_WINDOW_DAYS = 45
FUZZY_MIN_OVERLAP = 0.5

# Placeholder ids the extractors emit into header.document_id when they could
# not read a printed document number. These must never be treated as a PO's
# business number for linkage.
_PLACEHOLDER_DOC_IDS = frozenset(
    {
        "extracted",
        "po_extracted",
        "inv_extracted",
        "grn_extracted",
        "dc_extracted",
        "vlm_doc",
        "vlm_text_doc",
    }
)

_CONFIDENCE = {
    LinkMethod.EXPLICIT_REFERENCE: 0.98,
    LinkMethod.VENDOR_AMOUNT_DATE: 0.80,
    LinkMethod.FUZZY: 0.60,
}


def _norm(s: str | None) -> str:
    return (s or "").strip().casefold()


def _vendor_of(doc: ExtractedDocument) -> str:
    return _norm(doc.header.vendor_name.value if doc.header.vendor_name else None)


def _po_business_number(doc: ExtractedDocument) -> str:
    """A purchase order's *printed* number (e.g. ``PO-2026-118``), normalized.

    The regex extractors write the printed number into ``header.document_id``
    (see po_extractor ``po_number`` handling); the top-level
    ``ExtractedDocument.document_id`` is a per-upload hash (``doc_XXXX``)
    assigned at ingest. Linking on the hash was the Phase-7 cluster bug: an
    invoice citing ``PO-2026-118`` could never match a PO keyed by its hash, so
    the three-way-match checks silently SKIPped. Prefer the printed header id;
    fall back to ``po_reference`` (the VLM path may put the PO's own number
    there); ignore placeholders and the ingest hash.
    """
    hid = (doc.header.document_id or "").strip()
    if hid and hid not in _PLACEHOLDER_DOC_IDS and not hid.startswith("doc_"):
        return _norm(hid)
    ref = doc.header.po_reference
    return _norm(ref.value if ref else None)


def _po_ref_of(doc: ExtractedDocument) -> str:
    if doc.doc_type == DocumentType.PURCHASE_ORDER:
        return _po_business_number(doc)
    ref = doc.header.po_reference
    return _norm(ref.value if ref else None)


def _date_of(doc: ExtractedDocument) -> date | None:
    h = doc.header
    for pv in (h.invoice_date, h.order_date, h.delivery_date, h.grn_date):
        if pv is not None:
            try:
                return date.fromisoformat(pv.value)
            except ValueError:
                continue
    return None


def _amount_of(doc: ExtractedDocument) -> Decimal | None:
    if doc.header.grand_total is not None:
        try:
            return doc.header.grand_total.decimal_value
        except ValueError:
            return None
    return None


def _descriptions_of(doc: ExtractedDocument) -> set[str]:
    return {_norm(li.description.value) for li in doc.line_items}


def _link(doc: ExtractedDocument, method: LinkMethod) -> DocumentLink:
    return DocumentLink(
        document_id=doc.document_id,
        doc_type=doc.doc_type,
        method=method,
        confidence=_CONFIDENCE[method],
    )


def identity_scope(doc: ExtractedDocument) -> tuple[str, str, str]:
    h = doc.header
    supplier = h.vendor_gstin or h.vendor_name
    buyer = h.buyer_gstin or h.buyer_name
    return (
        doc.tenant_id,
        _norm(buyer.value if buyer else None),
        _norm(supplier.value if supplier else None),
    )


def business_number(doc: ExtractedDocument) -> str:
    h = doc.header
    value = {
        DocumentType.INVOICE: h.invoice_number,
        DocumentType.PURCHASE_ORDER: h.po_number,
        DocumentType.DELIVERY_CHALLAN: h.challan_number,
        DocumentType.GOODS_RECEIPT_NOTE: h.grn_number,
        DocumentType.CERTIFICATE_OF_ORIGIN: h.certificate_number,
    }.get(doc.doc_type)
    if value and value.value.strip():
        return _norm(value.value)
    if doc.doc_type == DocumentType.PURCHASE_ORDER and h.po_reference:
        return _norm(h.po_reference.value)
    printed = h.document_id
    if (
        printed
        and printed not in _PLACEHOLDER_DOC_IDS
        and not printed.startswith(("doc_", "upload_"))
    ):
        return _norm(printed)
    return ""


def duplicate_key(doc: ExtractedDocument) -> str:
    import json

    return json.dumps([*identity_scope(doc), doc.doc_type.value, business_number(doc)])


def near_duplicate_key(doc: ExtractedDocument) -> str | None:
    import json

    amount, when = _amount_of(doc), _date_of(doc)
    if amount is None or when is None:
        return None
    currency = doc.header.grand_total.currency if doc.header.grand_total else None
    return json.dumps(
        [
            *identity_scope(doc),
            doc.doc_type.value,
            str(amount.normalize()),
            when.isoformat(),
            currency,
        ]
    )


def _dates_close(a: ExtractedDocument, b: ExtractedDocument) -> bool:
    first, second = _date_of(a), _date_of(b)
    return (
        first is not None and second is not None and abs((first - second).days) <= DATE_WINDOW_DAYS
    )


def build_clusters(documents: list[ExtractedDocument]) -> list[TransactionCluster]:
    """Stable scoped anchors; inferred links remain candidates requiring review."""
    import hashlib
    import json

    clusters: dict[str, TransactionCluster] = {}
    unanchored = []
    for doc in sorted(documents, key=lambda d: (d.tenant_id, d.document_id)):
        ref = (
            business_number(doc) if doc.doc_type == DocumentType.PURCHASE_ORDER else _po_ref_of(doc)
        )
        scope = identity_scope(doc)
        if ref and scope[2]:
            key = json.dumps([*scope, ref])
            cid = "cluster-" + hashlib.sha256(key.encode()).hexdigest()[:24]
            c = clusters.setdefault(key, TransactionCluster(cluster_id=cid))
            c.documents.append(doc)
            c.links.append(_link(doc, LinkMethod.EXPLICIT_REFERENCE))
            if not scope[1]:
                c.review_reasons = [
                    "Buyer identity is missing; transaction identity requires review"
                ]
        else:
            unanchored.append(doc)
    anchors = list(clusters.values())
    for c in anchors:
        if len(c.of_type(DocumentType.PURCHASE_ORDER)) > 1:
            c.review_reasons.append(
                "Multiple purchase orders share the business identity; resolve revisions"
            )
    for doc in unanchored:
        candidates = []
        for c in anchors:
            # Only compare against explicit anchors, never an earlier inferred document.
            if any(
                identity_scope(m) == identity_scope(doc)
                and _vendor_of(doc)
                and (
                    (
                        _amount_of(m) is not None
                        and _amount_of(m) == _amount_of(doc)
                        and _dates_close(m, doc)
                    )
                    or bool(_descriptions_of(m) & _descriptions_of(doc))
                )
                for m in c.documents
            ):
                candidates.append(c.cluster_id)
        reasons = (
            ["Unconfirmed transaction candidates: " + ", ".join(sorted(candidates))]
            if candidates
            else ["No confirmed transaction reference"]
        )
        cid = (
            "cluster-solo-"
            + hashlib.sha256(f"{doc.tenant_id}:{doc.document_id}".encode()).hexdigest()[:24]
        )
        clusters[cid] = TransactionCluster(cluster_id=cid, documents=[doc], review_reasons=reasons)
    return sorted(clusters.values(), key=lambda c: c.cluster_id)


def build_corpus_index(documents: list[ExtractedDocument]) -> CorpusIndex:
    index = CorpusIndex()
    for doc in documents:
        if identity_scope(doc)[2] and business_number(doc):
            index.by_vendor_docnum.setdefault(duplicate_key(doc), []).append(doc.document_id)
        key = near_duplicate_key(doc)
        if key and identity_scope(doc)[2]:
            index.by_vendor_amount_date.setdefault(key, []).append(doc.document_id)
    return index
