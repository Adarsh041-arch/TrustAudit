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
_PLACEHOLDER_DOC_IDS = frozenset({
    "extracted", "po_extracted", "inv_extracted", "grn_extracted",
    "dc_extracted", "vlm_doc", "vlm_text_doc",
})

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


def build_clusters(documents: list[ExtractedDocument]) -> list[TransactionCluster]:
    """Group documents into transaction clusters.

    A cluster is anchored on a PO number where one is referenced; documents
    with no explicit reference fall back to (vendor, amount, date-window),
    then fuzzy vendor+description matching against existing clusters.
    """
    clusters: dict[str, TransactionCluster] = {}
    unanchored: list[ExtractedDocument] = []

    # Pass 1 — explicit references anchor clusters by PO number.
    for doc in documents:
        po_ref = _po_ref_of(doc)
        if po_ref:
            cluster = clusters.get(po_ref)
            if cluster is None:
                cluster = TransactionCluster(cluster_id=f"cluster-{po_ref}")
                clusters[po_ref] = cluster
            cluster.documents.append(doc)
            cluster.links.append(_link(doc, LinkMethod.EXPLICIT_REFERENCE))
        else:
            unanchored.append(doc)

    # Pass 2 — (vendor, amount, date-window) against anchored clusters.
    still_unanchored: list[ExtractedDocument] = []
    for doc in unanchored:
        vendor, amount, doc_date = _vendor_of(doc), _amount_of(doc), _date_of(doc)
        placed = False
        if vendor and amount is not None and doc_date is not None:
            for cluster in clusters.values():
                for member in cluster.documents:
                    m_date = _date_of(member)
                    if (
                        _vendor_of(member) == vendor
                        and _amount_of(member) == amount
                        and m_date is not None
                        and abs((m_date - doc_date).days) <= DATE_WINDOW_DAYS
                    ):
                        cluster.documents.append(doc)
                        cluster.links.append(_link(doc, LinkMethod.VENDOR_AMOUNT_DATE))
                        placed = True
                        break
                if placed:
                    break
        if not placed:
            still_unanchored.append(doc)

    # Pass 3 — fuzzy: same vendor + line-description overlap.
    for doc in still_unanchored:
        vendor, descs = _vendor_of(doc), _descriptions_of(doc)
        placed = False
        if vendor and descs:
            for cluster in clusters.values():
                for member in cluster.documents:
                    m_descs = _descriptions_of(member)
                    if _vendor_of(member) != vendor or not m_descs:
                        continue
                    overlap = len(descs & m_descs) / min(len(descs), len(m_descs))
                    if overlap >= FUZZY_MIN_OVERLAP:
                        cluster.documents.append(doc)
                        cluster.links.append(_link(doc, LinkMethod.FUZZY))
                        placed = True
                        break
                if placed:
                    break
        if not placed:
            # Singleton cluster: the document stands alone (no link to record).
            cid = f"cluster-solo-{_norm(doc.document_id)}"
            clusters[cid] = TransactionCluster(cluster_id=cid, documents=[doc])

    return list(clusters.values())


def build_corpus_index(documents: list[ExtractedDocument]) -> CorpusIndex:
    """Per-tenant duplicate-detection index (PHASES_V2 §4 Phase 6)."""
    index = CorpusIndex()
    for doc in documents:
        vendor = _vendor_of(doc)
        docnum = _norm(doc.document_id)
        if vendor and docnum:
            index.by_vendor_docnum.setdefault(
                f"{vendor}||{docnum}", []).append(doc.document_id)
        amount, doc_date = _amount_of(doc), _date_of(doc)
        if vendor and amount is not None and doc_date is not None:
            # Near-duplicate key is doc-type-scoped: a certificate, PO, or
            # contract that merely shares a vendor/amount/date with an invoice
            # is NOT a duplicate. Only same-kind documents can duplicate.
            key = f"{vendor}||{doc.doc_type.value}||{amount}||{doc_date.isoformat()}"
            index.by_vendor_amount_date.setdefault(key, []).append(doc.document_id)
    return index
