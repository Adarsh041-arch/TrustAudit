"""Tests for the SSE streaming path (new_requirements.md §6, Phase 2).

These stay fully offline: the autouse fixtures in ``conftest.py`` remove
``NVIDIA_API_KEY`` and stub OCR to unavailable, so an upload produces
regex + OCR(unavailable) + arithmetic + metadata evidence and no VLM /
contradictions — exactly like the synchronous path it mirrors.

The streaming endpoints are additive: the synchronous ``POST /upload`` contract
is covered by ``test_server_v2.py`` and must stay green (regression guard here).
"""

from __future__ import annotations

import asyncio
import json
import threading
from io import BytesIO
from typing import Any

import fitz
from fastapi.testclient import TestClient

from audit_v2 import server
from audit_v2.pipeline.events import PipelineStep, StepEvent, StepStatus
from audit_v2.pipeline.streaming import SENTINEL, JobRegistry, QueueSink
from audit_v2.server import app


from pathlib import Path


def _make_sample_pdf() -> bytes:
    sample = Path(__file__).parent.parent / "sample_docs" / "Commercial_Invoice_INV-2026-453.pdf"
    if sample.exists():
        return sample.read_bytes()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        "INVOICE #INV-2026-0715\nVendor: NewTech Solutions\nTotal: $1,250.00\n"
        "Date: 2026-07-15\nItem: Server License Qty: 1 Price: $1250.00",
    )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


MINIMAL_PDF = _make_sample_pdf()


class RecordingSink:
    """A ``ProgressSink`` that just collects every event, for assertions."""

    def __init__(self) -> None:
        self.events: list[StepEvent] = []

    def emit(self, event: StepEvent) -> None:
        self.events.append(event)


# ─── Unit: the thread→loop bridge ────────────────────────────────────────────


def test_queue_sink_bridges_thread_to_loop():
    """QueueSink.emit is called from the worker thread; the event must arrive on
    the event loop's (non-thread-safe) asyncio.Queue via call_soon_threadsafe."""

    async def scenario() -> StepEvent:
        loop = asyncio.get_running_loop()
        job = JobRegistry().create("tenant_default", loop)
        sink = QueueSink(job)
        event = StepEvent(
            document_id="doc_x", step=PipelineStep.CLASSIFY, status=StepStatus.OK
        )
        # Emit from a *different* thread, exactly as the pipeline worker does.
        worker = threading.Thread(target=sink.emit, args=(event,))
        worker.start()
        worker.join()
        return await asyncio.wait_for(job.queue.get(), timeout=2.0)

    got = asyncio.run(scenario())
    assert got.document_id == "doc_x"
    assert got.step == PipelineStep.CLASSIFY


def test_finish_sets_result_then_enqueues_sentinel():
    """finish() must set status/result *before* enqueuing the sentinel, so the
    SSE generator sees a populated result the moment it reads the sentinel."""

    async def scenario() -> tuple[Any, Any]:
        loop = asyncio.get_running_loop()
        registry = JobRegistry()
        job = registry.create("tenant_default", loop)
        registry.finish(job, result={"count": 3})
        item = await asyncio.wait_for(job.queue.get(), timeout=2.0)
        return job, item

    job, item = asyncio.run(scenario())
    assert item is SENTINEL
    assert job.status == "done"
    assert job.result == {"count": 3}


def test_finish_with_error_sets_error_status():
    async def scenario() -> Any:
        loop = asyncio.get_running_loop()
        registry = JobRegistry()
        job = registry.create("tenant_default", loop)
        registry.finish(job, error="boom")
        await asyncio.wait_for(job.queue.get(), timeout=2.0)
        return job

    job = asyncio.run(scenario())
    assert job.status == "error"
    assert job.error == "boom"
    assert job.result is None


# ─── Unit: the batch emits the RECEIVED/SCORE/DONE lifecycle around the pipeline


def test_process_documents_emits_lifecycle_steps():
    """_process_documents brackets each doc with RECEIVED..SCORE..DONE and
    threads the sink into run_document_pipeline (so CLASSIFY etc. appear too)."""
    sink = RecordingSink()
    payload = [("invoice.pdf", MINIMAL_PDF, "application/pdf")]

    result = server._process_documents(payload, "tenant_default", sink)

    steps = {e.step for e in sink.events}
    # Server-emitted bracket steps.
    assert PipelineStep.RECEIVED in steps
    assert PipelineStep.SCORE in steps
    assert PipelineStep.DONE in steps
    # Pipeline-emitted steps prove the sink was threaded all the way through.
    assert PipelineStep.CLASSIFY in steps
    assert PipelineStep.ARITHMETIC in steps

    received = [e for e in sink.events if e.step == PipelineStep.RECEIVED]
    assert received and received[0].detail == "invoice.pdf"
    # RECEIVED must precede DONE for a given document.
    order = [e.step for e in sink.events if e.document_id == received[0].document_id]
    assert order.index(PipelineStep.RECEIVED) < order.index(PipelineStep.DONE)
    assert result["count"] == 1


# ─── Endpoint: start a stream job ────────────────────────────────────────────


def test_upload_stream_returns_job_id():
    with TestClient(app) as client:
        res = client.post(
            "/api/v2/audit/upload/stream",
            files={"files": ("invoice.pdf", BytesIO(MINIMAL_PDF), "application/pdf")},
        )
        assert res.status_code == 200
        job_id = res.json()["job_id"]
        assert job_id.startswith("job_")
        # Drain the job so no background task is left pending at portal shutdown.
        _drain_stream(client, job_id)


def test_upload_stream_rejects_empty():
    with TestClient(app) as client:
        res = client.post("/api/v2/audit/upload/stream", files={})
    assert res.status_code in (400, 422)


# ─── Endpoint: the SSE stream itself ─────────────────────────────────────────


def _drain_stream(client: TestClient, job_id: str) -> tuple[list[str], dict | None]:
    """Consume an SSE stream, returning (event names, parsed result payload)."""
    events: list[str] = []
    result: dict | None = None
    with client.stream("GET", f"/api/v2/audit/stream/{job_id}") as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        current = None
        for line in res.iter_lines():
            if line.startswith("event:"):
                current = line.split(":", 1)[1].strip()
                events.append(current)
            elif line.startswith("data:") and current == "result":
                result = json.loads(line.split(":", 1)[1].strip())
                break
            elif line.startswith("data:") and current == "error":
                result = json.loads(line.split(":", 1)[1].strip())
                break
    return events, result


def test_stream_emits_open_steps_then_result():
    with TestClient(app) as client:
        job_id = client.post(
            "/api/v2/audit/upload/stream",
            files={"files": ("invoice.pdf", BytesIO(MINIMAL_PDF), "application/pdf")},
        ).json()["job_id"]

        events, result = _drain_stream(client, job_id)

    assert events[0] == "open"
    assert "step" in events
    assert events[-1] == "result"
    assert result is not None
    assert result["count"] == 1
    # The streamed result frame carries the same enriched payload as the sync path.
    dr = result["document_results"][0]
    assert dr["document_name"] == "invoice.pdf"
    assert isinstance(dr["evidences"], list) and dr["evidences"]
    assert dr["contradictions"] == []  # offline: no VLM cross-check


def test_result_endpoint_returns_done_after_stream():
    with TestClient(app) as client:
        job_id = client.post(
            "/api/v2/audit/upload/stream",
            files={"files": ("invoice.pdf", BytesIO(MINIMAL_PDF), "application/pdf")},
        ).json()["job_id"]

        # Draining guarantees the background job finished.
        _drain_stream(client, job_id)
        res = client.get(f"/api/v2/audit/result/{job_id}")

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "done"
    assert body["result"]["count"] == 1


# ─── Endpoint: unknown-job handling ──────────────────────────────────────────


def test_stream_unknown_job_returns_404():
    with TestClient(app) as client:
        res = client.get("/api/v2/audit/stream/job_does_not_exist")
    assert res.status_code == 404


def test_result_unknown_job_returns_404():
    with TestClient(app) as client:
        res = client.get("/api/v2/audit/result/job_does_not_exist")
    assert res.status_code == 404
