import asyncio
import threading

import pytest
from fastapi.testclient import TestClient

import audit_v2.server as server
from audit_v2.orchestration import local_jobs
from audit_v2.persistence.backup import create, restore, verify
from audit_v2.persistence.operational_store import OperationalStore
from audit_v2.pipeline.evidence_pipeline import DocumentPipelineResult
from audit_v2.pipeline.events import NullProgressSink
from tests.test_product_reliability import complete, inv


def fake_document(**kwargs):
    document = complete(inv(doc_id=kwargs["document_id"]))
    document.tenant_id = kwargs["tenant_id"]
    return DocumentPipelineResult(document_id=document.document_id,
                                  doc_type=document.doc_type, document=document)


def test_correction_retains_original_and_rejects_stale_revision(monkeypatch):
    monkeypatch.setattr(server, "run_document_pipeline", fake_document)
    monkeypatch.setattr(server, "generate_preview", lambda *args: "preview")
    result = server._process_documents([("invoice.pdf", b"original", "application/pdf")],
                                       "tenant_default", NullProgressSink())
    document_id = result["document_results"][0]["document_id"]
    client = TestClient(server.app)
    original = client.get(f"/api/v2/documents/{document_id}/revision").json()
    payload = {"expected_revision": original["revision"], "reason": "Reviewed source total",
               "changes": [{"path": "header.grand_total", "value": "123", "page": 1,
                            "source_quote": "Grand total 123"}]}
    changed = client.post(f"/api/v2/documents/{document_id}/corrections", json=payload)
    assert changed.status_code == 200, changed.text
    assert not changed.json()["document_results"][0]["passed"]
    assert client.post(f"/api/v2/documents/{document_id}/corrections", json=payload).status_code == 409
    current = client.get(f"/api/v2/documents/{document_id}/revision").json()
    assert current["document"]["header"]["grand_total"]["value"] == "123"
    assert current["document"]["content_hash"] == original["document"]["content_hash"]
    assert current["corrections"][0]["original_document"] == original["document"]
    item = next(i for i in server.REVIEW_QUEUE.pending_items if i.document_id == document_id)
    denied = client.post("/api/v2/audit/review", json={
        "item_id": item.item_id, "action": "confirm", "expected_version": item.version,
    })
    assert denied.status_code == 409


def test_backup_restore_roundtrip_and_tampering(tmp_path):
    source = tmp_path / "source"
    store = OperationalStore(source / "operational.sqlite3")
    with store.transaction("tenant-a") as tx:
        tx.save({"documents": {"d": {"total": "100.00001"}}, "reviews": []})
    backup = tmp_path / "backup"
    create(source, backup)
    destination = tmp_path / "restored"
    restore(backup, destination)
    with OperationalStore(destination / "operational.sqlite3").transaction("tenant-a") as tx:
        assert tx.load()["documents"]["d"]["total"] == "100.00001"
    with pytest.raises(FileExistsError):
        restore(backup, destination)
    (backup / "operational.sqlite3").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        verify(backup)


@pytest.mark.asyncio
async def test_retained_job_recovers_without_resubmitting_sources(monkeypatch):
    calls = []
    def extraction(**kwargs):
        calls.append(kwargs["document_id"])
        return fake_document(**kwargs)
    monkeypatch.setattr(server, "run_document_pipeline", extraction)
    monkeypatch.setattr(server, "generate_preview", lambda *args: "")
    local_jobs.register("recover", "job-recover", [("invoice.pdf", b"source", "application/pdf")])
    assert await local_jobs.result("recover", "job-recover") == {"status": "running"}
    await local_jobs._running[("recover", "job-recover")]
    recovered = await local_jobs.result("recover", "job-recover")
    assert recovered["status"] == "done"
    again = await local_jobs.result("recover", "job-recover")
    assert again == recovered and len(calls) == 1
    with pytest.raises(Exception) as error:
        await local_jobs.result("another-tenant", "job-recover")
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_cancellation_before_commit_never_saves_a_decision(monkeypatch):
    started, release = threading.Event(), threading.Event()
    def blocked(**kwargs):
        started.set()
        if not release.wait(timeout=10):
            raise RuntimeError("test timed out")
        return fake_document(**kwargs)
    monkeypatch.setattr(server, "run_document_pipeline", blocked)
    local_jobs.register("cancel", "job-cancel", [("invoice.pdf", b"source", "application/pdf")])
    await local_jobs.result("cancel", "job-cancel")
    task = local_jobs._running[("cancel", "job-cancel")]
    try:
        assert await asyncio.to_thread(started.wait, 5)
        await local_jobs.cancel("cancel", "job-cancel")
    finally:
        release.set()
    await task
    with server.OPERATIONAL_STORE.transaction("cancel") as tx:
        state = tx.load()
        assert not state.get("documents") and not state.get("operations")
    assert (await local_jobs.result("cancel", "job-cancel"))["status"] == "failed"
