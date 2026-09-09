"""Release regressions for the confirmed false-clearance failures."""
from collections import defaultdict
from itertools import permutations
import runpy

from audit_v2.domain.correlation import build_clusters, build_corpus_index
from audit_v2.domain.decision import decide_document
from audit_v2.domain.models import FindingStatus
from audit_v2.domain.validators import duplicate, threeway
from evaluation.measure_v2 import score_findings, score_extraction
from evaluation.metrics import ConfusionMatrix, determinism_score

helpers = runpy.run_path("tests/test_correlation.py")
po, inv, grn, line, ctx, pv = (helpers[k] for k in ("po", "inv", "grn", "line", "ctx", "pv"))


def complete(doc):
    doc.header.buyer_name = pv("Buyer One")
    for li in doc.line_items:
        li.quantity_unit = pv("each")
        li.unit_price.currency = "INR"
    for v in (doc.header.grand_total, doc.header.subtotal):
        if v:
            v.currency = "INR"
    return doc


def test_unmatched_lines_never_pass():
    p = complete(po(lines=[line(1,"Widget","10","100","1000")]))
    i = complete(inv(lines=[line(1,"Unrelated","10","100","1000")]))
    g = complete(grn(lines=p.line_items))
    c = build_clusters([p,i,g])[0]
    for check, fn in [("CHK-XDOC-PRICE-001",threeway.check_price_matches_po),
                      ("CHK-XDOC-QTY-001",threeway.check_invoiced_vs_received)]:
        result = fn(ctx(i,check,cluster=c))
        assert result.status == FindingStatus.NOT_RUN
        assert result.coverage["matched_lines"] == 0


def test_cumulative_receipts_cannot_be_reused():
    items = [line(1,"Widget","10","100","1000")]
    docs = [complete(po(lines=items)), complete(grn(lines=items)),
            complete(inv(doc_id="INV-1",lines=items)), complete(inv(doc_id="INV-2",lines=items))]
    c = build_clusters(docs)[0]
    for i in docs[2:]:
        r = threeway.check_invoiced_vs_received(ctx(i,"CHK-XDOC-QTY-001",cluster=c))
        assert r.status == FindingStatus.FAIL
        assert len(r.evidence) == 3


def test_supplier_tenant_and_buyer_separate_clusters():
    docs = [complete(po(doc_id="PO-1")), complete(po(doc_id="PO-1")), complete(po(doc_id="PO-1"))]
    docs[1].header.vendor_name = pv("Other supplier")
    docs[2].tenant_id = "other"
    assert len(build_clusters(docs)) == 3
    docs[2].tenant_id = docs[0].tenant_id
    docs[2].header.buyer_name = pv("Other buyer")
    assert len(build_clusters(docs)) == 3


def test_matching_is_order_invariant():
    docs = [complete(po()), complete(inv()), complete(grn())]
    assert len({str([c.model_dump() for c in build_clusters(list(order))])
                for order in permutations(docs)}) == 1


def test_printed_duplicate_with_changed_amount_and_date():
    a = complete(inv(doc_id="upload_a",total="100",inv_date="2026-06-10"))
    b = complete(inv(doc_id="upload_b",total="200",inv_date="2026-06-11"))
    a.header.invoice_number = b.header.invoice_number = pv("INV-REAL-1")
    result = duplicate.check_duplicate_document(ctx(b,"CHK-DUP-DOC-001",corpus_index=build_corpus_index([a,b])))
    assert result.status == FindingStatus.FAIL


def test_missing_required_checks_prevents_clearance():
    d = complete(inv())
    decision = decide_document(d, [], list(helpers['CATALOG'].values()))
    assert decision.status == "INCOMPLETE"
    assert not decision.passed


def test_known_defect_abstention_is_counted():
    matrices = defaultdict(ConfusionMatrix)
    misses = []
    score_findings({"document_id":"x","expected_findings":[{"check_id":"CHK-ARITH-LINE-001","expected_status":"FAIL"}]},
                   {"findings":[{"check_id":"CHK-ARITH-LINE-001","status":"NEEDS_REVIEW"}]},
                   matrices,misses,[],[],[])
    assert matrices['arithmetic'].fn == 1
    assert len(misses) == 1


def test_missing_extraction_counts_and_line_multiplicity():
    stats = {}
    score_extraction({"expected_fields":{"subtotal":"10"}, "expected_lines":[]}, {"document":None}, stats)
    assert stats['subtotal']['fn'] == 1
    assert determinism_score({'a': True}, {'a': True, 'b': True}) == 0.5


def test_label_and_row_grounding_prevents_value_swaps():
    from audit_v2.extraction.grounding import ground_instance
    from audit_v2.extraction.schemas import InvoiceExtraction
    candidate = InvoiceExtraction(subtotal="118", grand_total="100")
    result = ground_instance(candidate, "Subtotal 100\nGrand Total 118", 1)
    assert result.instance.subtotal is None
    assert result.instance.grand_total is None
    candidate = InvoiceExtraction.model_validate({"line_items":[{
        "description":"Widget A", "quantity":"2", "unit_price":"10", "line_total":"999"}]})
    result = ground_instance(candidate, "Widget A 2 10 20\nWidget B 1 999 999",1)
    assert result.instance.line_items == []


def test_operational_store_rollback_restart_and_tenant_boundary(tmp_path):
    from audit_v2.persistence.operational_store import OperationalStore
    path = tmp_path / "operations.db"
    store = OperationalStore(path)
    with store.transaction("a") as tx:
        tx.save({"money":"1234567890.1234", "review":"pending"})
    try:
        with store.transaction("a") as tx:
            tx.save({"money":"wrong"})
            raise RuntimeError("worker terminated")
    except RuntimeError:
        pass
    restarted = OperationalStore(path)
    with restarted.transaction("a") as tx:
        assert tx.load()["money"] == "1234567890.1234"
    with restarted.transaction("b") as tx:
        assert tx.load() is None


def test_authenticated_tenant_and_actor_boundaries(monkeypatch, tmp_path):
    import hashlib, json
    from fastapi.testclient import TestClient
    import audit_v2.server as server
    from audit_v2.persistence.operational_store import OperationalStore
    monkeypatch.setattr(server, "OPERATIONAL_STORE", OperationalStore(tmp_path / "auth.db"))
    monkeypatch.setenv("V2_AUTH_MODE", "token")
    accounts = [{"actor_id":"alice", "tenant_id":"a", "role":"viewer",
                 "token_sha256":hashlib.sha256(b"test-token").hexdigest()}]
    monkeypatch.setenv("V2_AUTH_ACCOUNTS", json.dumps(accounts))
    client = TestClient(server.app)
    assert client.get("/api/v2/audit/findings").status_code == 401
    headers = {"Authorization":"Bearer test-token"}
    assert client.get("/api/v2/audit/findings?tenant_id=b",headers=headers).status_code == 403
    assert client.get("/api/v2/audit/findings",headers=headers).json()['tenant_id'] == 'a'
    assert client.post("/api/v2/audit/review",headers=headers,json={"item_id":"x", "reviewer_id":"admin", "action":"confirm"}).status_code == 403
    assert client.get("/api/v2/audit/result/other-job",headers=headers).status_code == 404


def test_review_conflict_and_annotations_keep_history():
    from audit_v2.orchestration.review_queue import ReviewAction, ReviewQueue
    from audit_v2.domain.models import Finding, Severity
    f = Finding(finding_id="f",check_id="CHK-XDOC-QTY-001",document_id="d",tenant_id="t",
                status=FindingStatus.FAIL,severity=Severity.HIGH,message="Mismatch",
                decision_fingerprint="hash",ruleset_version="1")
    q=ReviewQueue(); item=q.enqueue(f,"d","t")
    q.submit_review(item.item_id,"alice",ReviewAction.ANNOTATE,expected_version=0)
    assert item.status == 'PENDING' and len(item.history) == 1
    import pytest
    with pytest.raises(ValueError,match="conflict"):
        q.submit_review(item.item_id,"bob",ReviewAction.CONFIRM,expected_version=0)
    q.submit_review(item.item_id,"bob",ReviewAction.ESCALATE,expected_version=1)
    assert item in q.pending_items
    assert len(item.history) == 2


def test_release_switch_never_overrides_failure(monkeypatch):
    from audit_v2.domain.decision import AuditDecision
    from audit_v2.domain.release import apply_release_gate
    monkeypatch.delenv("V2_AUTO_CLEARANCE_ENABLED", raising=False)
    assert apply_release_gate(AuditDecision(status="PASS")).status == "NEEDS_REVIEW"
    assert apply_release_gate(AuditDecision(status="FAIL")).status == "FAIL"
    monkeypatch.setenv("V2_AUTO_CLEARANCE_ENABLED", "true")
    assert apply_release_gate(AuditDecision(status="PASS")).passed


def test_durable_retry_reuses_committed_results(monkeypatch):
    import pytest
    import audit_v2.server as server
    from audit_v2.pipeline.evidence_pipeline import DocumentPipelineResult
    from audit_v2.pipeline.events import NullProgressSink
    calls = []
    def extract(**kwargs):
        calls.append(kwargs["document_id"])
        document = complete(inv(doc_id=kwargs["document_id"]))
        document.tenant_id = kwargs["tenant_id"]
        return DocumentPipelineResult(document_id=document.document_id,
                                      doc_type=document.doc_type, document=document)
    monkeypatch.setattr(server, "run_document_pipeline", extract)
    monkeypatch.setattr(server, "generate_preview", lambda *args: "")
    payload = [("invoice.pdf", b"same-original", "application/pdf")]
    first = server._process_documents(payload, "retry-test", NullProgressSink(), operation_id="job1")
    ids = [f["finding_id"] for f in first["findings"]]
    second = server._process_documents(payload, "retry-test", NullProgressSink(), operation_id="job1")
    assert len(calls) == 1
    assert [f["finding_id"] for f in second["findings"]] == ids
    assert second["session_id"] == first["session_id"]
    with pytest.raises(ValueError, match="different inputs"):
        server._process_documents([("invoice.pdf", b"changed", "application/pdf")],
                                  "retry-test", NullProgressSink(), operation_id="job1")


def test_artifacts_are_atomic_and_tenant_scoped(tmp_path, monkeypatch):
    import pytest
    from audit_v2.persistence.artifact_store import ArtifactStore
    monkeypatch.delenv("V2_ARTIFACT_BUCKET", raising=False)
    store = ArtifactStore(tmp_path)
    digest = store.put("one", b"source bytes")
    assert store.put("one", b"source bytes") == digest
    assert store.get("one", digest) == b"source bytes"
    with pytest.raises(FileNotFoundError):
        store.get("two", digest)
    with pytest.raises(ValueError):
        store.get("one", "../../outside")


def test_product_evaluation_counts_abstentions_and_errors():
    from evaluation.product_reliability import summarize
    rows = [{"expected": "FAIL", "actual": "NEEDS_REVIEW"},
            {"expected": "PASS", "actual": "ERROR"},
            {"expected": "FAIL", "actual": "PASS"}]
    report = summarize(rows, "synthetic")
    assert report["expected_documents"] == 3
    assert report["defect_recall"] == 0
    assert report["false_clearances"] == 1
    assert report["errors"] == 1
    assert not report["release_gate_passed"]


def test_grounding_rejects_swapped_columns_within_same_row():
    from audit_v2.extraction.grounding import ground_instance
    from audit_v2.extraction.schemas import InvoiceExtraction
    candidate = InvoiceExtraction.model_validate({"line_items": [{
        "description": "Widget", "quantity": "10", "unit_price": "2", "line_total": "20"}]})
    transcript = "| Description | Qty | Unit Price | Amount |\n| Widget | 2 | 10 | 20 |"
    assert ground_instance(candidate, transcript, 1).instance.line_items == []


def test_failed_upload_remains_in_saved_workspace(monkeypatch):
    import audit_v2.server as server
    from audit_v2.domain.models import DocumentType
    from audit_v2.pipeline.evidence_pipeline import DocumentPipelineResult
    from audit_v2.pipeline.events import NullProgressSink
    def failed(**kwargs):
        return DocumentPipelineResult(document_id=kwargs["document_id"],
                                      doc_type=DocumentType.UNKNOWN, document=None,
                                      error="could not extract")
    monkeypatch.setattr(server, "run_document_pipeline", failed)
    result = server._process_documents([("broken.pdf", b"broken", "application/pdf")],
                                       "failure-test", NullProgressSink())
    assert result["accepted_count"] == 1
    assert result["documents_incomplete"] == 1
    assert len(result["document_results"]) == 1
    document = result["document_results"][0]
    assert not document["passed"] and document["document_status"] == "FAILED"
    with server.OPERATIONAL_STORE.transaction("failure-test") as tx:
        assert document["document_id"] in tx.load()["results"]


def test_kill_switch_applies_to_saved_pass_without_rewriting_history(monkeypatch):
    from audit_v2.server import _present_result
    monkeypatch.delenv("V2_AUTO_CLEARANCE_ENABLED", raising=False)
    saved = {"passed": True, "audit_status": "PASS", "decision": {"status": "PASS", "blockers": []}}
    shown = _present_result(saved)
    assert shown["passed"] is False and shown["audit_status"] == "NEEDS_REVIEW"
    assert saved["passed"] is True and saved["decision"]["blockers"] == []


def test_tampered_operational_state_cannot_be_hydrated(tmp_path):
    import pytest
    import sqlite3
    from audit_v2.persistence.operational_store import OperationalStore
    store = OperationalStore(tmp_path / "integrity.db")
    with store.transaction("a") as tx:
        tx.save({"passed": False})
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE audit_operational_state SET payload = ? WHERE tenant_id = ?",
                           ('{"passed": true}', "a"))
    with pytest.raises(ValueError, match="integrity"):
        with store.transaction("a") as tx:
            tx.load()


def test_published_finding_schema_matches_runtime():
    import json
    from pathlib import Path
    from jsonschema import validate
    from audit_v2.domain.models import Finding, Severity
    finding = Finding(finding_id="fnd_123456789012", check_id="CHK-XDOC-QTY-001",
                      document_id="doc_" + "a" * 32, tenant_id="t",
                      status=FindingStatus.NOT_RUN, severity=Severity.HIGH,
                      message="Missing receipt", decision_fingerprint="sha256:" + "a" * 64,
                      ruleset_version="1", coverage={"required_lines": 1, "matched_lines": 0})
    schema = json.loads(Path("contracts/schemas/finding.json").read_text(encoding="utf-8"))
    validate(finding.model_dump(mode="json"), schema)
