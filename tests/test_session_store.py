from audit_v2.persistence.session_store import AuditSessionStore, RecordingSink
from audit_v2.pipeline.events import (
    NullProgressSink,
    PipelineStep,
    StepEvent,
    StepStatus,
)


def test_session_trace_survives_new_store_instance(tmp_path) -> None:
    path = tmp_path / "sessions.sqlite3"
    store = AuditSessionStore(path)
    session_id = store.create_session("tenant-a")
    sink = RecordingSink(store, session_id, NullProgressSink())
    sink.emit(StepEvent(
        document_id="doc-1", step=PipelineStep.CLASSIFY,
        status=StepStatus.OK, detail="invoice", data={"confidence": 0.99},
    ))
    store.record_layer(
        session_id, "doc-1", sink.next_sequence("doc-1"),
        "qwen_ollama_transcription", "evidence", "page transcribed",
        {"text": "INVOICE"},
    )
    store.record_document(
        session_id, "doc-1", "invoice.pdf", "application/pdf", b"pdf",
        {"doc_type": "invoice"}, {"audit_status": "PASS"},
    )
    store.complete(session_id, {"documents_passed": 1})

    reopened = AuditSessionStore(path)
    trace = reopened.trace(session_id, "doc-1", "tenant-a")

    assert trace is not None
    assert trace["canonical"]["doc_type"] == "invoice"
    assert [item["layer"] for item in trace["layers"]] == [
        "classify", "qwen_ollama_transcription",
    ]


def test_sessions_and_traces_are_tenant_isolated(tmp_path) -> None:
    store = AuditSessionStore(tmp_path / "sessions.sqlite3")
    session_id = store.create_session("tenant-a")
    store.record_document(
        session_id, "doc-1", "invoice.pdf", "application/pdf", b"pdf", {}, {},
    )

    assert store.get_session(session_id, "tenant-b") is None
    assert store.trace(session_id, "doc-1", "tenant-b") is None
    assert store.list_sessions("tenant-b") == []
