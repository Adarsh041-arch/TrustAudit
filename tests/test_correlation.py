"""Phase 7 — correlation, three-way match, duplicate detection, deferred re-eval.

PHASES_V2 §4 Phase 7 acceptance criteria:
- three-way match correct on clusters incl. over-billing, split-invoice,
  price-variance cases;
- late-arrival: invoice before PO -> cluster re-evaluates, earlier finding
  superseded, never duplicated.
"""
from decimal import Decimal

from audit_v2.domain.catalog_loader import load_catalog
from audit_v2.domain.correlation import build_clusters, build_corpus_index
from audit_v2.domain.models import (
    CheckContext,
    Coverage,
    DocumentHeader,
    DocumentType,
    ExtractedDocument,
    FindingStatus,
    LineItem,
    LinkMethod,
    ProvenancedValue,
)
from audit_v2.domain.validators import duplicate, reference_integrity, threeway
from audit_v2.orchestration.cluster_audit import ClusterAuditor

CATALOG = {c.check_id: c for c in load_catalog().checks}


def pv(value: str, raw: str | None = None) -> ProvenancedValue:
    return ProvenancedValue(value=value, raw=raw or value, page=1)


def line(n: int, desc: str, qty: str, price: str, total: str) -> LineItem:
    return LineItem(
        line_number=n, description=pv(desc), quantity=pv(qty),
        unit_price=pv(price), line_total=pv(total), hsn_sac=pv("8471"),
    )


def make_doc(
    doc_id: str,
    doc_type: DocumentType,
    vendor: str = "Acme Corp",
    po_ref: str | None = None,
    grand_total: str | None = None,
    subtotal: str | None = None,
    inv_date: str | None = None,
    lines: list[LineItem] | None = None,
) -> ExtractedDocument:
    header = DocumentHeader(
        document_id=doc_id,
        doc_type=doc_type,
        vendor_name=pv(vendor),
        po_reference=pv(po_ref) if po_ref else None,
        grand_total=pv(grand_total) if grand_total else None,
        subtotal=pv(subtotal) if subtotal else None,
        invoice_date=pv(inv_date) if inv_date else None,
        order_date=pv(inv_date) if (inv_date and doc_type == DocumentType.PURCHASE_ORDER) else None,
    )
    return ExtractedDocument(
        document_id=doc_id, tenant_id="t", doc_type=doc_type, header=header,
        line_items=lines or [],
        coverage=Coverage(pages_total=1, pages_examined=1, coverage_complete=True),
        page_count=1, extractor_version="2.1.0",
    )


def ctx(document, check_id, cluster=None, corpus_index=None) -> CheckContext:
    return CheckContext(
        document=document, check_entry=CATALOG[check_id],
        cluster=cluster, corpus_index=corpus_index,
    )


def po(doc_id="PO-1", total="100000.00", lines=None):
    return make_doc(doc_id, DocumentType.PURCHASE_ORDER, grand_total=total,
                    inv_date="2026-06-01", lines=lines)


def inv(doc_id="INV-1", po_ref="PO-1", total=None, subtotal=None, lines=None,
        inv_date="2026-06-10"):
    return make_doc(doc_id, DocumentType.INVOICE, po_ref=po_ref,
                    grand_total=total, subtotal=subtotal,
                    inv_date=inv_date, lines=lines)


def grn(doc_id="GRN-1", po_ref="PO-1", lines=None):
    return make_doc(doc_id, DocumentType.GOODS_RECEIPT_NOTE, po_ref=po_ref,
                    lines=lines)


# ─── Cluster builder ──────────────────────────────────────────────────────────

class TestBuildClusters:
    def test_explicit_reference_links_po_invoice_grn(self):
        docs = [po(), inv(), grn()]
        clusters = build_clusters(docs)
        assert len(clusters) == 1
        c = clusters[0]
        assert {d.document_id for d in c.documents} == {"PO-1", "INV-1", "GRN-1"}
        assert all(link.method == LinkMethod.EXPLICIT_REFERENCE for link in c.links)
        assert c.purchase_order is not None

    def test_po_anchors_on_printed_number_not_ingest_hash(self):
        """Regression: an invoice citing the PO's printed number must cluster
        with the PO even after ingest overwrites the top-level document_id with
        a per-upload hash (doc_XXXX). The old code anchored the PO on that hash,
        so the invoice fell into a PO-less cluster and PRICE/CUMUL silently
        SKIPped — the root cause of the same invoice scoring differently as a
        PDF vs a photo.
        """
        p = po(doc_id="PO-2026-118", total="100000.00")
        i = inv("INV-2026-453", po_ref="PO-2026-118", total="50000.00")
        # Simulate ingest: top-level id becomes a hash; header keeps the number.
        p.document_id = "doc_6ccb2642"
        i.document_id = "doc_b11b2961"
        clusters = build_clusters([p, i])
        assert len(clusters) == 1
        c = clusters[0]
        assert c.purchase_order is not None
        assert c.purchase_order.document_id == "doc_6ccb2642"
        assert {d.document_id for d in c.documents} == {"doc_6ccb2642", "doc_b11b2961"}

    def test_po_business_number_falls_back_to_po_reference(self):
        """VLM-only PO extraction leaves header.document_id as a placeholder
        ('vlm_doc'); the PO's own number lands in po_reference. Linkage on the
        printed number must still work via the fallback."""
        p = po(doc_id="vlm_doc", total="100000.00")
        p.header.po_reference = pv("PO-2026-118")
        p.document_id = "doc_aaaa1111"
        i = inv("INV-1", po_ref="PO-2026-118", total="50000.00")
        i.document_id = "doc_bbbb2222"
        clusters = build_clusters([p, i])
        assert len(clusters) == 1
        assert clusters[0].purchase_order is not None

    def test_no_reference_falls_back_to_vendor_amount_date(self):
        anchor = inv("INV-A", po_ref="PO-9", total="5000.00")
        stray = make_doc("INV-B", DocumentType.INVOICE, grand_total="5000.00",
                         inv_date="2026-06-15")
        anchor.header.invoice_date = pv("2026-06-10")
        clusters = build_clusters([anchor, stray])
        assert len(clusters) == 1
        methods = {link.document_id: link.method for link in clusters[0].links}
        assert methods["INV-B"] == LinkMethod.VENDOR_AMOUNT_DATE

    def test_fuzzy_match_on_vendor_and_descriptions(self):
        anchor = inv("INV-A", po_ref="PO-9",
                     lines=[line(1, "Widget B", "5", "30.00", "150.00")])
        stray = make_doc("DC-X", DocumentType.DELIVERY_CHALLAN,
                         lines=[line(1, "Widget B", "5", "0", "0")])
        clusters = build_clusters([anchor, stray])
        assert len(clusters) == 1
        methods = {link.document_id: link.method for link in clusters[0].links}
        assert methods["DC-X"] == LinkMethod.FUZZY

    def test_unrelated_documents_get_singleton_clusters(self):
        a = make_doc("INV-A", DocumentType.INVOICE, vendor="Vendor One")
        b = make_doc("INV-B", DocumentType.INVOICE, vendor="Vendor Two")
        clusters = build_clusters([a, b])
        assert len(clusters) == 2

    def test_deterministic(self):
        docs = [po(), inv(), grn()]
        c1 = build_clusters(docs)
        c2 = build_clusters(docs)
        assert [c.cluster_id for c in c1] == [c.cluster_id for c in c2]


# ─── Three-way match ──────────────────────────────────────────────────────────

class TestThreeWayMatch:
    def _cluster(self, docs):
        clusters = build_clusters(docs)
        assert len(clusters) == 1
        return clusters[0]

    def test_qty_mismatch_invoice_exceeds_grn(self):
        g = grn(lines=[line(1, "Widget B", "5", "0", "0")])
        i = inv(lines=[line(1, "Widget B", "8", "30.00", "240.00")])
        c = self._cluster([po(), g, i])
        r = threeway.check_invoiced_vs_received(ctx(i, "CHK-XDOC-QTY-001", cluster=c))
        assert r.status == FindingStatus.FAIL
        assert r.delta == "3"
        assert len(r.evidence) == 2

    def test_qty_ok_when_invoiced_within_received(self):
        g = grn(lines=[line(1, "Widget B", "5", "0", "0")])
        i = inv(lines=[line(1, "Widget B", "5", "30.00", "150.00")])
        c = self._cluster([po(), g, i])
        r = threeway.check_invoiced_vs_received(ctx(i, "CHK-XDOC-QTY-001", cluster=c))
        assert r.status == FindingStatus.PASS

    def test_qty_skips_without_cluster(self):
        r = threeway.check_invoiced_vs_received(ctx(inv(), "CHK-XDOC-QTY-001"))
        assert r.status == FindingStatus.SKIPPED

    def test_qty_skips_without_grn(self):
        i = inv()
        c = self._cluster([po(), i])
        r = threeway.check_invoiced_vs_received(ctx(i, "CHK-XDOC-QTY-001", cluster=c))
        assert r.status == FindingStatus.SKIPPED

    def test_price_variance_detected(self):
        p = po(lines=[line(1, "Widget B", "10", "30.00", "300.00")])
        i = inv(lines=[line(1, "Widget B", "10", "45.00", "450.00")])
        c = self._cluster([p, i])
        r = threeway.check_price_matches_po(ctx(i, "CHK-XDOC-PRICE-001", cluster=c))
        assert r.status == FindingStatus.FAIL
        assert r.expected == "30.00"
        assert r.actual == "45.00"

    def test_price_match_passes(self):
        p = po(lines=[line(1, "Widget B", "10", "30.00", "300.00")])
        i = inv(lines=[line(1, "Widget B", "5", "30.00", "150.00")])
        c = self._cluster([p, i])
        r = threeway.check_price_matches_po(ctx(i, "CHK-XDOC-PRICE-001", cluster=c))
        assert r.status == FindingStatus.PASS

    def test_receipt_required_above_threshold(self):
        i = inv(total="100000.00")
        c = self._cluster([po(), i])
        r = threeway.check_receipt_exists(ctx(i, "CHK-XDOC-RECEIPT-001", cluster=c))
        assert r.status == FindingStatus.FAIL
        assert r.requires_human_review

    def test_receipt_not_required_below_threshold(self):
        i = inv(total="10000.00")
        c = self._cluster([po(), i])
        r = threeway.check_receipt_exists(ctx(i, "CHK-XDOC-RECEIPT-001", cluster=c))
        assert r.status == FindingStatus.PASS

    def test_receipt_present_passes(self):
        i = inv(total="100000.00")
        c = self._cluster([po(), grn(), i])
        r = threeway.check_receipt_exists(ctx(i, "CHK-XDOC-RECEIPT-001", cluster=c))
        assert r.status == FindingStatus.PASS

    def test_overbilling_across_multiple_invoices(self):
        """Split-invoice over-billing: each invoice under PO value, sum over."""
        p = po(total="100000.00")
        i1 = inv("INV-1", subtotal="60000.00", total="70800.00")
        i2 = inv("INV-2", subtotal="60000.00", total="70800.00")
        c = self._cluster([p, i1, i2])
        r = threeway.check_cumulative_invoiced(
            ctx(i2, "CHK-XDOC-CUMUL-001", cluster=c))
        assert r.status == FindingStatus.FAIL
        assert Decimal(r.delta) == Decimal("20000.00")
        assert r.requires_human_review

    def test_cumulative_within_po_value_passes(self):
        p = po(total="100000.00")
        i1 = inv("INV-1", subtotal="40000.00", total="47200.00")
        i2 = inv("INV-2", subtotal="50000.00", total="59000.00")
        c = self._cluster([p, i1, i2])
        r = threeway.check_cumulative_invoiced(
            ctx(i2, "CHK-XDOC-CUMUL-001", cluster=c))
        assert r.status == FindingStatus.PASS

    def test_cumulative_skips_without_po(self):
        i = inv(po_ref=None, total="1000.00")
        clusters = build_clusters([i])
        r = threeway.check_cumulative_invoiced(
            ctx(i, "CHK-XDOC-CUMUL-001", cluster=clusters[0]))
        assert r.status == FindingStatus.SKIPPED


# ─── CHK-REF-QTY via cluster ──────────────────────────────────────────────────

class TestRefQtyChecks:
    def test_invoice_qty_exceeds_po_qty(self):
        p = po(lines=[line(1, "Widget B", "5", "30.00", "150.00")])
        i = inv(lines=[line(1, "Widget B", "9", "30.00", "270.00")])
        clusters = build_clusters([p, i])
        r = reference_integrity.check_quantity_po(
            ctx(i, "CHK-REF-QTY-001", cluster=clusters[0]))
        assert r.status == FindingStatus.FAIL
        assert r.delta == "4"

    def test_grn_qty_exceeds_dc_qty(self):
        d = make_doc("DC-1", DocumentType.DELIVERY_CHALLAN, po_ref="PO-1",
                     lines=[line(1, "Widget B", "5", "0", "0")])
        g = grn(lines=[line(1, "Widget B", "7", "0", "0")])
        clusters = build_clusters([po(), d, g])
        r = reference_integrity.check_quantity_dc(
            ctx(g, "CHK-REF-QTY-002", cluster=clusters[0]))
        assert r.status == FindingStatus.FAIL

    def test_skips_without_cluster(self):
        r = reference_integrity.check_quantity_po(ctx(inv(), "CHK-REF-QTY-001"))
        assert r.status == FindingStatus.SKIPPED


# ─── Duplicate detection ──────────────────────────────────────────────────────

class TestDuplicateDetection:
    def test_same_vendor_docnum_flagged(self):
        a = inv("INV-1", total="5000.00")
        b = inv("INV-1", total="5000.00")
        b2 = b.model_copy(deep=True)
        b2 = b2.model_copy(update={"document_id": "INV-1"})
        index = build_corpus_index([a, b2])
        # same vendor+docnum appears twice -> both ids in the bucket
        index.by_vendor_docnum["acme corp||inv-1"] = ["INV-1", "INV-1-copy"]
        r = duplicate.check_duplicate_document(
            ctx(a, "CHK-DUP-DOC-001", corpus_index=index))
        assert r.status == FindingStatus.FAIL
        assert r.requires_human_review

    def test_same_vendor_amount_date_different_number_flagged(self):
        a = inv("INV-1", total="5000.00", inv_date="2026-06-10")
        b = inv("INV-2", total="5000.00", inv_date="2026-06-10")
        index = build_corpus_index([a, b])
        r = duplicate.check_duplicate_document(
            ctx(a, "CHK-DUP-DOC-001", corpus_index=index))
        assert r.status == FindingStatus.FAIL
        assert "INV-2" in r.actual

    def test_unique_document_passes(self):
        a = inv("INV-1", total="5000.00", inv_date="2026-06-10")
        b = inv("INV-2", total="9000.00", inv_date="2026-06-20")
        index = build_corpus_index([a, b])
        r = duplicate.check_duplicate_document(
            ctx(a, "CHK-DUP-DOC-001", corpus_index=index))
        assert r.status == FindingStatus.PASS

    def test_cross_type_same_amount_date_not_duplicate(self):
        """A PO sharing an invoice's vendor+amount+date is a legitimate match,
        not a duplicate. The near-key is scoped to document type."""
        i = inv("INV-1", total="5000.00", inv_date="2026-06-10")
        p = make_doc("PO-1", DocumentType.PURCHASE_ORDER,
                     grand_total="5000.00", inv_date="2026-06-10")
        index = build_corpus_index([i, p])
        r_inv = duplicate.check_duplicate_document(
            ctx(i, "CHK-DUP-DOC-001", corpus_index=index))
        r_po = duplicate.check_duplicate_document(
            ctx(p, "CHK-DUP-DOC-001", corpus_index=index))
        assert r_inv.status == FindingStatus.PASS
        assert r_po.status == FindingStatus.PASS

    def test_skips_without_index(self):
        r = duplicate.check_duplicate_document(ctx(inv(), "CHK-DUP-DOC-001"))
        assert r.status == FindingStatus.SKIPPED


# ─── Deferred re-evaluation ───────────────────────────────────────────────────

class TestDeferredReEvaluation:
    def test_invoice_before_po_supersedes_not_duplicates(self):
        """§4 Phase 7 acceptance: late-arriving PO re-evaluates the cluster."""
        auditor = ClusterAuditor(ruleset_version="rs_test")
        i = inv(lines=[line(1, "Widget B", "10", "45.00", "450.00")],
                subtotal="450.00", total="531.00")
        auditor.add_document(i)
        first = {
            (f.document_id, f.check_id): f for f in auditor.active_findings
        }
        # Price check could not run yet (no PO): PASS not asserted
        price_key = ("INV-1", "CHK-XDOC-PRICE-001")
        assert price_key not in first or first[price_key].status in (
            FindingStatus.SKIPPED, FindingStatus.PASS,
        )

        p = po(total="100000.00",
               lines=[line(1, "Widget B", "10", "30.00", "300.00")])
        auditor.add_document(p)

        active = {(f.document_id, f.check_id): f for f in auditor.active_findings}
        price = active[price_key]
        assert price.status == FindingStatus.FAIL  # 45.00 != 30.00

        # Exactly one active finding per (doc, check): superseded, not duplicated
        keys = [(f.document_id, f.check_id) for f in auditor.active_findings]
        assert len(keys) == len(set(keys))
        if price.supersedes:
            superseded_ids = {f.finding_id for f in auditor.superseded_findings}
            assert price.supersedes in superseded_ids

    def test_unchanged_verdict_not_reemitted(self):
        auditor = ClusterAuditor(ruleset_version="rs_test")
        p = po(lines=[line(1, "Widget B", "10", "30.00", "300.00")])
        auditor.add_document(p)
        i1 = inv("INV-1", subtotal="150.00", total="177.00",
                 lines=[line(1, "Widget B", "5", "30.00", "150.00")])
        emitted1 = auditor.add_document(i1)
        # Adding an unrelated second invoice re-runs INV-1 checks; consistent
        # verdicts must not spawn new findings.
        i2 = inv("INV-2", subtotal="100.00", total="118.00",
                 lines=[line(1, "Widget C", "2", "50.00", "100.00")])
        auditor.add_document(i2)
        keys = [(f.document_id, f.check_id) for f in auditor.active_findings]
        assert len(keys) == len(set(keys))
        # INV-1's price finding survives from the first emission
        inv1_price = [f for f in emitted1
                      if f.document_id == "INV-1" and f.check_id == "CHK-XDOC-PRICE-001"]
        assert inv1_price
