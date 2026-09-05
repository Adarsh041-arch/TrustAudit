# Phase 2 — Real-Time SSE Streaming + Frontend Evidence/Contradiction UI

> **Status:** planned, not started. Phase 1 (backend evidence pipeline, synchronous) is complete and green (506 passed, 8 skipped).
> **Scope of this document:** the full implementation plan for Phase 2 as locked in the approved re-architecture plan (`new_requirements.md` §6, §8).
> **Author's note:** every file path / line number below reflects the code as of this writing; treat line numbers as approximate anchors.

---

## 0. What Phase 2 delivers

Per `new_requirements.md`:
- **§6 — Real-time progress:** the frontend shows, live, *which pipeline step is running for which document* (classify → regex → OCR → VLM → self-check → arithmetic → cross-check → score → done).
- **§8 — Complete dashboards:** each document card renders its ordered **evidence trail** and any **contradictions**; the overall dashboard aggregates them.

Locked decisions carried from Phase 1 that constrain this phase:
- **Transport = SSE streaming** (Server-Sent Events), not WebSockets/polling.
- **Deterministic authority is unchanged** — Phase 2 is pure presentation/transport; it must not alter scoring, reconciliation, or the deterministic-vs-LLM authority boundary.
- **Phased & additive** — Phase 2 must not break Phase 1's synchronous `/upload` contract or its tests.
- **No secrets** — nothing in this phase reads, logs, or commits `.env` values.

---

## 1. Guiding principles (hard constraints)

1. **Additive, not a rewrite.** The synchronous `POST /api/v2/audit/upload` stays exactly as-is (same request, same response). Existing `tests/test_server_v2.py` contract tests must remain green untouched. Streaming is delivered through **new** endpoints.
2. **The pipeline does not change.** `run_document_pipeline` (`audit_v2/pipeline/evidence_pipeline.py:339`) already accepts `sink: ProgressSink` and already emits `StepEvent`s at every step. Phase 2 only supplies a *different sink* and a transport around it. No edits to `evidence_pipeline.py` logic.
3. **Graceful degradation preserved.** With no `NVIDIA_API_KEY` / no `rapidocr`, streaming still works — steps simply report `SKIP`, and the final result matches the offline sync response.
4. **The event loop must never block on network I/O.** VLM (`extract_structured → requests`) and cross-check (`run_cross_check → requests`) are blocking (`audit_v2/gateway/nvidia_gateway.py:16`). All document processing runs in a **worker thread**; the SSE generator drains a queue on the event loop.

---

## 2. Architecture

```
 Browser (AppV2)                         FastAPI (:8100)                    Worker thread
 ───────────────                         ───────────────                    ─────────────
 1. POST /upload/stream (multipart) ───▶ read file bytes
                                          create PipelineJob{queue}
                                          register JOBS[job_id]
                             ◀─── {job_id}   asyncio.create_task(_run_job) ─────▶ _process_documents(payload, sink=QueueSink)
 2. EventSource GET /stream/{job_id} ──▶ StreamingResponse(_event_stream)          │  run_document_pipeline(sink) per file
                                          │                                        │    emit(CLASSIFY..CROSS_CHECK)  ── sink.emit(StepEvent)
      ◀── event: step  {StepEvent} ───────┤◀───────── queue.get() ◀── call_soon_threadsafe(queue.put_nowait, ev) ──┘
      ◀── event: step  {StepEvent} ───────┤            (deterministic checks, scoring)  emit(SCORE), emit(DONE)
      ◀── event: result {UploadResponse}──┤◀── job.result set, sentinel enqueued ◀──── return response dict
 3. render DocumentCard(evidences,        └── (job kept for TTL; GET /result/{job_id} for reconnect)
      contradictions) + dashboard
```

**Key correctness point — the thread→loop bridge.** `sink.emit()` is called *from the worker thread*, but the SSE consumer awaits `queue.get()` *on the event loop*. `asyncio.Queue` is **not** thread-safe. The `QueueSink` must capture the running loop at job creation and push via `loop.call_soon_threadsafe(queue.put_nowait, event)`. This is mandatory, not optional.

**Why two steps (POST then EventSource GET)?** Browser `EventSource` is GET-only and cannot send a body, so it can't carry the multipart upload. The POST creates the job and returns a `job_id`; the `EventSource` then subscribes to that job. Because the job's `asyncio.Queue` is created *before* the worker starts, any events emitted before the client attaches are **buffered** in the queue — no early events are lost.

---

## 3. Backend work (`audit_v2/`)

### 3.1 Refactor: extract `_process_documents` (safe, behavior-preserving checkpoint)

**File:** `audit_v2/server.py`

The body of `upload_documents` (`server.py:296-540`) does per-file pipeline + batch (clusters, `CheckRunner.run_all`, findings, provenance, review queue, audit log) + `enrich_document` + response assembly. Extract everything after "read the files" into a shared, **bytes-based, sink-aware** function:

```python
# payload item: (filename, data: bytes, mime_type: str)
def _process_documents(
    payload: list[tuple[str, bytes, str]],
    tenant_id: str,
    sink: ProgressSink,
) -> dict[str, Any]:
    # ... exactly today's per-file + batch logic, but:
    #   - takes already-read bytes (not UploadFile — not thread-safe)
    #   - threads `sink` into run_document_pipeline(..., sink=sink)
    #   - emits SCORE per doc after enrich, and a final DONE
    #   - holds _PROCESS_LOCK around shared-store mutations
    ...
    return { ... same dict `upload_documents` returns today ... }
```

- **`upload_documents` (sync endpoint) becomes a thin wrapper** — read files, then off-load to a thread so the event loop stays free:
  ```python
  @app.post("/api/v2/audit/upload")
  async def upload_documents(files=File(...), tenant_id="tenant_default"):
      if not files: raise HTTPException(400, "No files provided for upload")
      payload = [(f.filename, await f.read(), f.content_type or "application/pdf") for f in files]
      return await asyncio.to_thread(_process_documents, payload, tenant_id, NullProgressSink())
  ```
  Response contract is **identical** → all Phase 1 tests still pass. The only change is it no longer blocks the loop.

- **Concurrency guard.** `_process_documents` mutates module-level `DOCUMENTS_STORE`, `EVIDENCE_STORE`, `CONTRADICTION_STORE`, `FINDINGS_STORE`, `AUDIT_LOG`, `PROVENANCE`, `REVIEW_QUEUE` and reads `build_clusters`/`build_corpus_index` over *all* docs. Two concurrent batches (one sync + one streaming) could race. Add a module-level `_PROCESS_LOCK = threading.Lock()` and hold it around the mutation-heavy body. This **serializes** concurrent uploads (they queue) — acceptable for a single-user app, and correct. Document the tradeoff inline.

- **New emitted steps.** `SCORE` and `DONE` are declared in `PipelineStep` but never emitted (the pipeline stops at `CROSS_CHECK`). In `_process_documents`, after each doc is enriched, `emit(sink, doc_id, PipelineStep.SCORE, StepStatus.OK, score=...)`; after the whole batch, `emit(sink, "", PipelineStep.DONE, StepStatus.OK, count=len(...))`.

- **New labeling step `RECEIVED`.** The frontend needs to map `document_id ↔ filename` to label progress rows, but `document_id` is assigned inside the loop. Add `RECEIVED = "received"` to `PipelineStep` (`audit_v2/pipeline/events.py:20`) and, at the top of each file's iteration, `emit(sink, document_id, PipelineStep.RECEIVED, StepStatus.OK, filename=filename)`. This is purely additive — the pipeline itself never emits it.

### 3.2 Job registry + `QueueSink`

**New file:** `audit_v2/pipeline/streaming.py`

```python
import asyncio, time, uuid
from dataclasses import dataclass, field
from audit_v2.pipeline.events import ProgressSink, StepEvent

_SENTINEL = object()  # terminal marker enqueued when the job finishes

@dataclass
class PipelineJob:
    job_id: str
    tenant_id: str
    queue: "asyncio.Queue"
    loop: "asyncio.AbstractEventLoop"
    status: str = "running"           # running | done | error
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)

class QueueSink:
    """ProgressSink that bridges worker-thread emits to the loop's asyncio.Queue."""
    def __init__(self, job: PipelineJob) -> None:
        self._job = job
    def emit(self, event: StepEvent) -> None:
        self._job.loop.call_soon_threadsafe(self._job.queue.put_nowait, event)

class JobRegistry:
    """In-memory job store with a bounded LRU + TTL (single process only)."""
    def __init__(self, max_jobs: int = 64, ttl_seconds: float = 1800): ...
    def create(self, tenant_id, loop) -> PipelineJob: ...   # makes queue, registers, evicts old
    def get(self, job_id) -> PipelineJob | None: ...
    def finish(self, job, result=None, error=None): ...     # set status/result, enqueue _SENTINEL
```

- `QueueSink` satisfies the existing `ProgressSink` Protocol (`events.py:52`) — no changes to the pipeline signature.
- `JobRegistry` eviction: cap at N most-recent + drop entries older than TTL, so memory can't grow unbounded when clients never connect / never fetch results.

### 3.3 New endpoints (all additive)

**File:** `audit_v2/server.py` (add `import asyncio`, `from fastapi.responses import StreamingResponse`, and the streaming imports; instantiate `JOBS = JobRegistry()`).

**a) `POST /api/v2/audit/upload/stream` → `{ "job_id": ... }`**
```python
@app.post("/api/v2/audit/upload/stream")
async def upload_documents_stream(files=File(...), tenant_id="tenant_default"):
    if not files: raise HTTPException(400, "No files provided for upload")
    payload = [(f.filename, await f.read(), f.content_type or "application/pdf") for f in files]
    loop = asyncio.get_running_loop()
    job = JOBS.create(tenant_id, loop)         # queue created BEFORE worker starts
    sink = QueueSink(job)
    async def _run_job():
        try:
            result = await asyncio.to_thread(_process_documents, payload, tenant_id, sink)
            JOBS.finish(job, result=result)
        except Exception as err:               # never leave a stream hanging
            logger.exception("stream job %s failed", job.job_id)
            JOBS.finish(job, error=str(err))
    asyncio.create_task(_run_job())
    return {"job_id": job.job_id}
```

**b) `GET /api/v2/audit/stream/{job_id}` → `text/event-stream`**
```python
def _sse(event: str, obj) -> str:
    return f"event: {event}\ndata: {json.dumps(obj, default=str)}\n\n"

@app.get("/api/v2/audit/stream/{job_id}")
async def stream_pipeline(job_id: str):
    job = JOBS.get(job_id)
    if job is None: raise HTTPException(404, "unknown job")
    async def _gen():
        yield _sse("open", {"job_id": job_id})
        while True:
            try:
                item = await asyncio.wait_for(job.queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"        # comment frame: defeats proxy idle-timeout
                continue
            if item is _SENTINEL:
                break
            yield _sse("step", item.model_dump(mode="json"))
        if job.error: yield _sse("error", {"message": job.error})
        else:         yield _sse("result", job.result)
    return StreamingResponse(_gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})
```
- `X-Accel-Buffering: no` + `Cache-Control: no-cache` defeat nginx/proxy buffering; the 15 s keepalive comment defeats idle-connection timeouts.
- Single-consumer queue: the terminal `result` frame carries the full `UploadResponse` dict (same shape as sync `/upload`), so the client needs no second call on the happy path.

**c) `GET /api/v2/audit/result/{job_id}` → final `UploadResponse` (reconnect fallback)**
```python
@app.get("/api/v2/audit/result/{job_id}")
async def get_job_result(job_id: str):
    job = JOBS.get(job_id)
    if job is None: raise HTTPException(404, "unknown job")
    if job.status == "running": return {"status": "running"}
    if job.error: raise HTTPException(500, job.error)
    return job.result
```
- Covers the EventSource-auto-reconnect-after-completion case: the queue is single-consumer, so a reconnect after the stream drained sees nothing — the client falls back to this endpoint.

### 3.4 Backend surfaces touched — summary
| File | Change |
|---|---|
| `audit_v2/pipeline/events.py` | add `RECEIVED` to `PipelineStep` (additive) |
| `audit_v2/pipeline/streaming.py` | **new** — `PipelineJob`, `QueueSink`, `JobRegistry`, `_SENTINEL` |
| `audit_v2/pipeline/__init__.py` | export the new streaming symbols |
| `audit_v2/server.py` | extract `_process_documents`; wrap sync `/upload` in `to_thread`; add `_PROCESS_LOCK`; emit `RECEIVED`/`SCORE`/`DONE`; add 3 endpoints + `JOBS` |
| `audit_v2/pipeline/evidence_pipeline.py` | **none** (already sink-aware) |
| `audit_v2/domain/evidence.py` | **none** |

---

## 4. Frontend work (`audit-frontend/src/`)

> Build stack: **Vite 8 + React 19** (`npm run dev` → port **5173**), Tailwind v4, `recharts`, `lucide-react`. AppV2 renders at `http://localhost:5173/?mode=v2`. Backend hardcoded to `http://localhost:8100/api/v2` (`api/api_v2.ts:7`).
>
> **Decoupling note:** `enrich_document` (`server.py:291-292`) **already returns** `evidences` + `contradictions` per document in *today's* sync response. So the rendering work (§4.4–4.6) is independent of the SSE work (§4.2–4.3) and can land first, verified against the existing sync `/upload`.

### 4.1 Types — `src/types/audit.ts`

Add (mirroring `audit_v2/domain/evidence.py` and `pipeline/events.py` exactly):
```ts
export type EvidenceNature =
  | 'metadata' | 'extracted_fields' | 'arithmetic_computation'
  | 'vlm_observations' | 'ocr+regex_observations'

export interface PipelineEvidence {
  evidence_id: string
  document_id: string
  nature: EvidenceNature
  source: string                 // regex | rapidocr | vlm | vlm_corrected | arithmetic | metadata
  payload: Record<string, unknown>
  summary: string
  confidence: number
  page: number | null
  created_at: string
}

export interface Contradiction {
  document_id: string
  nature: EvidenceNature
  evidence: string
  reason: string
  confidence: number
  severity: 'critical' | 'high' | 'medium' | 'low'
  conflicting_with: string | null
}

export type PipelineStepName =
  | 'received' | 'classify' | 'extract_regex' | 'extract_ocr' | 'extract_vlm'
  | 'vlm_selfcheck' | 'arithmetic' | 'cross_check' | 'score' | 'done'
export type StepStatus = 'start' | 'ok' | 'skip' | 'error'

export interface StepEvent {
  document_id: string
  step: PipelineStepName
  status: StepStatus
  detail: string
  data: Record<string, unknown>   // e.g. { filename, doc_type, score, contradictions }
}
```
Extend `DocumentAuditResult` (`types/audit.ts:27-45`) with:
```ts
  evidences: PipelineEvidence[]
  contradictions: Contradiction[]
```
(Optional, low-risk cleanup: give `UploadResponse.findings`/`analytics` real types instead of `any` — deferred, not required.)

### 4.2 API client — `src/api/api_v2.ts`

- **(Recommended) make the base URL overridable** for deploy flexibility, defaulting to today's value:
  ```ts
  export const V2_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8100/api/v2'
  ```
- **Add the streaming upload** (returns a job id):
  ```ts
  export async function uploadDocumentsStreamV2(files, tenantId='tenant_default'): Promise<{ job_id: string }> {
    const fd = new FormData(); Array.from(files).forEach(f => fd.append('files', f))
    const res = await fetch(`${V2_BASE}/audit/upload/stream?tenant_id=${encodeURIComponent(tenantId)}`,
      { method: 'POST', body: fd })
    if (!res.ok) throw new Error((await res.json().catch(()=>null))?.detail ?? `Upload failed ${res.status}`)
    return res.json()
  }
  ```
- **Add the SSE subscription** (thin `EventSource` wrapper, returns an unsubscribe fn):
  ```ts
  export function subscribePipeline(jobId, h: {
    onOpen?: () => void
    onStep: (e: StepEvent) => void
    onResult: (r: UploadResponse) => void
    onError: (msg: string) => void
  }): () => void {
    const es = new EventSource(`${V2_BASE}/audit/stream/${jobId}`)
    es.addEventListener('open',   () => h.onOpen?.())
    es.addEventListener('step',   e => h.onStep(JSON.parse((e as MessageEvent).data)))
    es.addEventListener('result', e => { h.onResult(JSON.parse((e as MessageEvent).data)); es.close() })
    es.addEventListener('error',  e => {
      const d = (e as MessageEvent).data
      h.onError(d ? JSON.parse(d).message : 'stream connection lost'); es.close()
    })
    return () => es.close()
  }
  ```
  - `EventSource` uses `withCredentials=false` by default, so the server's `allow_origins=['*']` CORS (`server.py:131`) is sufficient for the cross-origin (`5173`→`8100`) subscription.
  - Keep `uploadDocumentsV2` (the sync one) as the **fallback** path.

### 4.3 Upload flow — `src/AppV2.tsx`

- **New state** (near `AppV2.tsx:26-35`):
  ```ts
  const [pipeline, setPipeline] = useState<Record<string, { filename: string; steps: Record<string, StepStatus> }>>({})
  ```
  keyed by `document_id`; each `RECEIVED` event seeds `{filename, steps:{}}`, each subsequent event sets `steps[step] = status`.
- **Rewrite `handleUpload`** (`AppV2.tsx:42-67`) to the streaming flow, preserving all the existing post-success state updates:
  ```ts
  async function handleUpload() {
    if (!files?.length) return
    setUploading(true); setError(null); setPipeline({})
    try {
      const { job_id } = await uploadDocumentsStreamV2(files)
      subscribePipeline(job_id, {
        onStep: e => setPipeline(p => applyStep(p, e)),   // seeds on 'received', updates otherwise
        onResult: res => {
          setUploadResult(res)
          if (res.document_results?.length) setSelectedDocId(res.document_results[0].document_id)
          if (res.documents?.length) setAllDocuments(prev => [...prev, ...res.documents!])
          else if (res.document) setAllDocuments(prev => [...prev, res.document])
          setAllFindings(prev => [...prev, ...res.findings])
          if (res.document_results) setAllReportDocs(prev => [...prev, ...res.document_results])
          setUploading(false)
        },
        onError: msg => { setError(msg); setUploading(false) },
      })
    } catch (e) { setError(e instanceof Error ? e.message : 'Document ingestion failed'); setUploading(false) }
  }
  ```
  - Provide a **graceful fallback**: if `EventSource`/stream errors before any result, fall back to `uploadDocumentsV2` so a proxy that strips SSE still works. (Optional but recommended.)

### 4.4 New component — `src/components/PipelineProgress.tsx`

- **Props:** `{ pipeline: Record<string, { filename: string; steps: Record<string, StepStatus> }> }`.
- Renders **one row per document** (labelled by `filename` from the `received` event), and along each row the ordered steps as chips/icons:
  `RECEIVED → CLASSIFY → EXTRACT_REGEX → EXTRACT_OCR → EXTRACT_VLM → VLM_SELFCHECK → ARITHMETIC → CROSS_CHECK → SCORE → DONE`.
- Status → visual: `start` = pulsing/spinner, `ok` = green check, `skip` = grey dash, `error` = red x (use `lucide-react` icons already in the project; reuse Tailwind animations `scan`/`spin` from `index.css`).
- **Mounting:** replace the indeterminate `<ProcessingAnimation/>` at `AppV2.tsx:147` (gated on `uploading`) with `<PipelineProgress pipeline={pipeline} />` (optionally keep `ProcessingAnimation` as the pre-first-event placeholder).

### 4.5 Evidence + contradiction rendering — `DocumentCard` + two new components

- **`src/components/EvidenceTrail.tsx`** — props `{ evidences: PipelineEvidence[] }`. A collapsible accordion **mirroring `FailedRulesList.tsx`** (its local `open` state + `SeverityDot` pattern): list evidences in emitted order, each showing a `nature` badge, `source`, `summary`, `confidence`; expand to pretty-print `payload` (JSON). Order communicates the spec's ladder (regex→ocr→vlm→[vlm_corrected]→arithmetic→metadata).
- **`src/components/ContradictionList.tsx`** — props `{ contradictions: Contradiction[] }`. Severity-sorted list (reuse the severity color helper), each row: `nature` + `severity` badge, `reason`, the `evidence` text, `confidence`, and `conflicting_with`. Empty state: "No contradictions — evidences support each other." Guard the "advisory only" framing in copy (these never override deterministic findings).
- **`src/components/DocumentCard.tsx`** — after `<FailedRulesList rules={doc.failed_rules} />` (`DocumentCard.tsx:40`), add:
  ```tsx
  <ContradictionList contradictions={doc.contradictions ?? []} />
  <EvidenceTrail evidences={doc.evidences ?? []} />
  ```
  `DocumentCard` already receives the full `DocumentAuditResult`, so no prop plumbing is needed — only the two new fields on the type (§4.1).

### 4.6 Dashboard aggregation — `src/sections/DashboardSection.tsx`

- Add a **"Contradictions" `<MetricCard>`** = total across `documents.flatMap(d => d.contradictions ?? [])`.
- Add a small **contradictions-by-nature** bar (reuse the existing Recharts `BarChart` pattern already in this file). Keep the empty-state behavior.

### 4.7 Frontend surfaces touched — summary
| File | Change |
|---|---|
| `src/types/audit.ts` | new evidence/contradiction/step types; extend `DocumentAuditResult` |
| `src/api/api_v2.ts` | `uploadDocumentsStreamV2`, `subscribePipeline`, overridable `V2_BASE` |
| `src/AppV2.tsx` | `pipeline` state; rewrite `handleUpload` to stream; mount `PipelineProgress` |
| `src/components/PipelineProgress.tsx` | **new** per-doc step tracker |
| `src/components/EvidenceTrail.tsx` | **new** evidence accordion |
| `src/components/ContradictionList.tsx` | **new** contradiction list |
| `src/components/DocumentCard.tsx` | mount the two new sections |
| `src/sections/DashboardSection.tsx` | contradictions metric + chart |

---

## 5. Tests

### 5.1 Backend (pytest, hermetic — network + OCR mocked, per Phase 1 conventions)
New `tests/test_streaming.py`:
- **`test_queue_sink_bridges_thread_to_loop`** — run a tiny function in a thread that calls `QueueSink.emit`; assert events arrive on the loop's queue in order (exercises `call_soon_threadsafe`).
- **`test_process_documents_emits_score_and_done`** — drive `_process_documents` with a capturing sink over a synthetic invoice; assert the emitted step sequence includes `RECEIVED … CROSS_CHECK SCORE DONE`, and the returned dict matches the sync response shape (has `document_results` with `evidences`/`contradictions`).
- **`test_upload_stream_returns_job_id`** — `POST /upload/stream` → 200 + `job_id`.
- **`test_stream_emits_events_then_result`** — use `TestClient.stream("GET", …)` (httpx streaming) to read the SSE frames; assert ≥1 `event: step` then a terminal `event: result` whose payload carries offline evidences (`regex`, `rapidocr`, `arithmetic`, `metadata`) and `contradictions == []`.
- **`test_stream_unknown_job_404`** and **`test_result_unknown_job_404`**.
- **Regression:** existing `tests/test_server_v2.py` sync-contract tests stay green unchanged (the wrapper preserves the response).

### 5.2 Frontend
The repo has **no JS test runner today** (lint is `oxlint`). Two options:
- **Recommended minimal:** add **Vitest + @testing-library/react** and cover (a) `subscribePipeline` event parsing with a mocked `EventSource`, (b) `PipelineProgress` rendering across `start/ok/skip/error`, (c) `ContradictionList`/`EvidenceTrail` render + empty states.
- **If keeping FE test-runner-free:** rely on the manual verification in §7 and `tsc -b` type-checking; still add the types so the compiler enforces the response shape.

---

## 6. Sequencing (each step independently verifiable; stop/commit points between)

1. **BE refactor** — extract `_process_documents`, wrap sync `/upload` in `to_thread`, add `_PROCESS_LOCK`. Run full suite → **must stay 506+ green**. *(No behavior change; safe checkpoint.)*
2. **BE streaming** — `pipeline/streaming.py`, `RECEIVED` step, `SCORE`/`DONE` emits, 3 endpoints, `JOBS`. Add `tests/test_streaming.py`.
3. **FE rendering (decoupled)** — types + `EvidenceTrail` + `ContradictionList` + `DocumentCard` + dashboard, verified against the *existing* sync `/upload`. *(Delivers §8 without touching transport.)*
4. **FE streaming** — streaming client + `pipeline` state + `handleUpload` rewrite + `PipelineProgress`. *(Delivers §6.)*
5. **End-to-end + degradation verification** (§7).

> This order means §8 (dashboards) is usable after step 3 even before streaming lands, and every step leaves the app working.

---

## 7. Verification (manual, Phase 2)

1. **Live, key present:** start backend (`venv/Scripts/python.exe -m uvicorn audit_v2.server:app --port 8100`) and `npm run dev`; open `http://localhost:5173/?mode=v2`. Upload a multi-doc batch → `PipelineProgress` shows each document advancing through steps in real time; on completion each `DocumentCard` shows the ordered `EvidenceTrail` (incl. `vlm`/`vlm_corrected` when the VLM ran) + any `Contradictions`; dashboard shows the contradictions metric.
2. **Offline (no `NVIDIA_API_KEY`):** steps still stream, `EXTRACT_VLM`/`CROSS_CHECK` show `SKIP`, result renders (regex→rapidocr→arithmetic→metadata), `contradictions: []`. *(This mirrors the Phase 1 offline smoke test, now streamed.)*
3. **Failure resilience:** kill the backend mid-stream → frontend surfaces an error (no crash, `uploading` clears); reconnect → `GET /result/{job_id}` returns the finished result if the job completed.
4. **Regression:** sync `/upload` tests green; V1 (`?mode=v2` off) unaffected.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Event loop blocked by VLM/cross-check `requests` calls | Process in a worker thread (`asyncio.to_thread`) for **both** the stream job and the sync `/upload` |
| `asyncio.Queue` mutated from a worker thread (data race / lost wakeups) | `QueueSink` uses `loop.call_soon_threadsafe(queue.put_nowait, event)` — **mandatory** |
| Early events emitted before the client's `EventSource` attaches | Queue is created at job registration, *before* the worker starts; unbounded buffering until drained |
| Proxy/browser buffers the SSE stream | `X-Accel-Buffering: no`, `Cache-Control: no-cache`, 15 s `: keepalive` comment frames |
| `JOBS` grows unbounded (clients never connect / never fetch) | `JobRegistry` LRU cap (N=64) + TTL (30 min) eviction |
| Concurrent uploads race shared in-memory stores | `_PROCESS_LOCK` serializes `_process_documents` (uploads queue) |
| Single-consumer queue → EventSource auto-reconnect after completion sees nothing | Terminal `event: result` on the happy path + `GET /result/{job_id}` fallback for reconnect |
| Base64 previews bloat the stream | Previews ride only the **final** `result` frame; `step` events are tiny (ids/counts) |
| `EventSource` is GET-only (no multipart body) | Two-step: `POST /upload/stream` → `job_id`, then `GET /stream/{job_id}` |
| CORS for cross-origin SSE | Existing `allow_origins=['*']`; `EventSource` is non-credentialed by default |

---

## 9. Explicitly out of scope (deferred / non-goals)

- Job **persistence across restarts** (in-memory only; a process restart drops in-flight jobs).
- **Auth** on the streaming endpoints (inherits the app's current open posture).
- **Multi-process / horizontal scale** (a single-process `asyncio.Queue`; would need Redis pub-sub or similar to scale out).
- **In-flight cancellation** of a running job (could add `POST /stream/{job_id}/cancel` later).
- Changing the deterministic scoring / reconciliation logic — **untouched by design**.
- Committing anything or touching `.env` — out of scope for this phase; no secrets are read or logged.

---

## 10. Definition of done

- All Phase 1 tests still green; new `tests/test_streaming.py` green; `tsc -b` clean.
- `?mode=v2` upload streams per-document step progress live and renders per-document evidence trails + contradictions, with a dashboard contradictions aggregate.
- Offline and backend-killed paths degrade without crashing.
- Sync `/upload` contract byte-for-byte unchanged.
