/**
 * Audit V2 API Client — Communicates with FastAPI on port :8100
 */

import type { DocumentAuditResult, PredictionInterval, StepEvent } from '../types/audit'

// Overridable for deployed frontends via Vite env (VITE_API_BASE); defaults to
// the local dev backend on :8100.
export const V2_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://localhost:8100/api/v2'

export type ExtractionMode = 'dual' | 'regex' | 'vlm' | 'vlm_text'

export interface ExtractionResultEntry {
  filename: string
  document_id: string
  doc_type: string
  is_vlm_fallback: boolean
  extraction_mode: ExtractionMode
  extractor_version: string
  pages: number
  disagreement_count: number
  disagreement_fields: string[]
  has_narrative_report: boolean
  evidence_count?: number
  contradiction_count?: number
  requires_human_review?: boolean
}

export interface UploadResponse {
  message: string
  document: any
  documents?: any[]
  findings: any[]
  cluster_id: string | null
  is_vlm_fallback: boolean
  requires_human_review: boolean
  extraction_results?: ExtractionResultEntry[]
  document_results: DocumentAuditResult[]
  prediction_interval: PredictionInterval
  analytics: any
  executive_summary: string
  documents_passed: number
  documents_failed: number
  documents_incomplete: number
  documents_review_required: number
}

export interface CopilotReply {
  answer: string
  ai_available: boolean
}

export async function askAuditCopilotV2(
  documentId: string,
  question: string,
  chatHistory: { role: 'user' | 'assistant'; content: string }[] = []
): Promise<CopilotReply> {
  const res = await fetch(`${V2_BASE}/copilot/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      document_id: documentId,
      question,
      chat_history: chatHistory.slice(-6),
    }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail || `Copilot request failed (${res.status})`)
  }
  return res.json()
}


export interface AuditLogResponse {
  tenant_id: string
  chain_valid: boolean
  verification_error: string | null
  entries: {
    entry_id: string
    action: string
    resource_type: string
    resource_id: string
    actor_id: string
    payload: any
    timestamp: string
    prev_hash: string
    hash_chain: string
  }[]
}

export interface ReviewQueueResponse {
  count: number
  pending_items: {
    item_id: string
    document_id: string
    priority_score: number
    finding: any
    created_at: string
    status: string
  }[]
  golden_set_candidates_count: number
}

export async function uploadDocumentsV2(
  files: FileList | File[],
  tenantId: string = 'tenant_default'
): Promise<UploadResponse> {
  const formData = new FormData()
  const fileArray = Array.from(files)
  fileArray.forEach((f) => formData.append('files', f))

  const res = await fetch(`${V2_BASE}/audit/upload?tenant_id=${encodeURIComponent(tenantId)}`, {
    method: 'POST',
    body: formData,
  })

  if (!res.ok) {
    const errorBody = await res.json().catch(() => null)
    throw new Error(errorBody?.detail || `Upload failed with status ${res.status}`)
  }

  return res.json()
}


// ─── Real-time streaming audit (SSE, new_requirements.md §6) ─────────────────

/**
 * Start a streaming audit job. Returns a `job_id` to subscribe to via
 * {@link subscribePipeline}. The final result frame carries the same
 * {@link UploadResponse} shape as the synchronous {@link uploadDocumentsV2}.
 */
export async function uploadDocumentsStreamV2(
  files: FileList | File[],
  tenantId: string = 'tenant_default'
): Promise<{ job_id: string }> {
  const formData = new FormData()
  Array.from(files).forEach((f) => formData.append('files', f))

  const res = await fetch(
    `${V2_BASE}/audit/upload/stream?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: 'POST', body: formData }
  )
  if (!res.ok) {
    const errorBody = await res.json().catch(() => null)
    throw new Error(errorBody?.detail || `Stream start failed with status ${res.status}`)
  }
  return res.json()
}

export interface PipelineHandlers {
  onOpen?: (jobId: string) => void
  onStep: (event: StepEvent) => void
  onResult: (result: UploadResponse) => void
  onError: (message: string) => void
}

/**
 * Subscribe to a job's pipeline progress over Server-Sent Events.
 *
 * Every frame is a *named* SSE event (`open` | `step` | `result` | `error`), so
 * we register per-name listeners rather than relying on the default `message`
 * handler. The server closes the stream after `result`/`error`; we `close()`
 * eagerly so the browser's EventSource does not auto-reconnect to a drained job.
 * A transport-level drop (distinguished by the absence of `event.data`) reports
 * an error so the caller can fall back to {@link fetchJobResult}.
 *
 * @returns an unsubscribe function that closes the stream.
 */
export function subscribePipeline(jobId: string, handlers: PipelineHandlers): () => void {
  const es = new EventSource(`${V2_BASE}/audit/stream/${encodeURIComponent(jobId)}`)
  let done = false

  const parse = <T,>(e: Event): T | null => {
    try {
      return JSON.parse((e as MessageEvent).data) as T
    } catch {
      return null
    }
  }

  es.addEventListener('open', (e) => {
    const payload = parse<{ job_id: string }>(e)
    if (payload) handlers.onOpen?.(payload.job_id)
  })

  es.addEventListener('step', (e) => {
    const payload = parse<StepEvent>(e)
    if (payload) handlers.onStep(payload)
  })

  es.addEventListener('result', (e) => {
    done = true
    es.close()
    const payload = parse<UploadResponse>(e)
    if (payload) handlers.onResult(payload)
    else handlers.onError('Received a malformed result from the audit stream')
  })

  // The server's own `error` frame carries data; a transport error does not.
  es.addEventListener('error', (e) => {
    if (done) return
    const payload = parse<{ message: string }>(e)
    if (payload) {
      done = true
      es.close()
      handlers.onError(payload.message)
    } else {
      // Connection dropped — stop retrying and let the caller poll for a result.
      done = true
      es.close()
      handlers.onError('Lost connection to the audit stream')
    }
  })

  return () => {
    done = true
    es.close()
  }
}

/** Reconnect fallback: fetch a finished job's result after the SSE dropped. */
export async function fetchJobResult(
  jobId: string
): Promise<{ status: 'running' } | { status: 'done'; result: UploadResponse }> {
  const res = await fetch(`${V2_BASE}/audit/result/${encodeURIComponent(jobId)}`)
  if (!res.ok) {
    const errorBody = await res.json().catch(() => null)
    throw new Error(errorBody?.detail || `Result fetch failed with status ${res.status}`)
  }
  return res.json()
}

export async function fetchFindingsV2(
  tenantId: string = 'tenant_default'
): Promise<any[]> {
  const res = await fetch(`${V2_BASE}/audit/findings?tenant_id=${encodeURIComponent(tenantId)}`)
  if (!res.ok) throw new Error(`Failed to fetch findings (${res.status})`)
  return res.json()
}

export interface EvalMetrics {
  accuracy: number | null
  precision: number | null
  recall: number | null
  f1_score: number | null
  false_positive_rate: number | null
  false_negative_rate: number | null
  average_latency_seconds: number | null
  average_confidence_score: number | null
}

export interface EvalResponse {
  metrics: EvalMetrics | null
  baselines?: any
}

export async function fetchEvalV2(): Promise<EvalResponse> {
  const res = await fetch(`${V2_BASE}/audit/eval`)
  if (!res.ok) throw new Error(`Eval fetch failed with status ${res.status}`)
  return res.json()
}

export async function downloadReportV2(
  format: 'docx' | 'pdf',
  documents: DocumentAuditResult[],
  findings: any[],
  auditTitle = 'Audit V2 Report',
  executiveSummary = '',
): Promise<Blob> {
  const res = await fetch(`${V2_BASE}/audit/report?format=${format}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ documents, findings, audit_title: auditTitle, executive_summary: executiveSummary }),
  })
  if (!res.ok) throw new Error(`Report download failed with status ${res.status}`)
  return res.blob()
}

export async function fetchAuditLogV2(tenantId: string = 'tenant_default'): Promise<AuditLogResponse> {
  const res = await fetch(`${V2_BASE}/audit/log?tenant_id=${encodeURIComponent(tenantId)}`)
  if (!res.ok) throw new Error(`Failed to fetch audit log (${res.status})`)
  return res.json()
}

export async function fetchReviewQueueV2(): Promise<ReviewQueueResponse> {
  const res = await fetch(`${V2_BASE}/audit/review-queue`)
  if (!res.ok) throw new Error(`Failed to fetch review queue (${res.status})`)
  return res.json()
}

export async function submitReviewV2(
  itemId: string,
  action: 'confirm' | 'reject_as_false_positive' | 'escalate',
  reviewerId: string = 'reviewer_1',
  comments?: string
): Promise<any> {
  const res = await fetch(`${V2_BASE}/audit/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      item_id: itemId,
      action,
      reviewer_id: reviewerId,
      comments,
    }),
  })
  if (!res.ok) {
    const errorBody = await res.json().catch(() => null)
    throw new Error(errorBody?.detail || `Review submission failed (${res.status})`)
  }
  return res.json()
}
